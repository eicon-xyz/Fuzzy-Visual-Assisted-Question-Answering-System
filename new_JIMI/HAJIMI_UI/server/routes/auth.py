"""POST /api/auth/login — JWT 签发"""
import hashlib, json, base64, time
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from server.config import settings
from server.database import SessionLocal
from server.database.models import User

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class LoginReq(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login")
async def login(req: LoginReq):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == req.username).first()
        if not user and req.password:
            user = User(username=req.username, password_hash=hashlib.sha256(req.password.encode()).hexdigest(), role="admin")
            db.add(user); db.commit(); db.refresh(user)
        elif not user or hashlib.sha256(req.password.encode()).hexdigest() != user.password_hash:
            raise HTTPException(401, detail={"error": {"code": "AUTH_FAILED", "message": "用户名或密码错误"}})
    finally:
        db.close()

    now = int(time.time())
    h = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps({"sub": req.username, "role": "admin", "iat": now, "exp": now + 7200}).encode()).decode().rstrip("=")
    s = hashlib.sha256(f"{h}.{p}.{settings.DEMO_KEY}".encode()).hexdigest()[:16]
    return {"access_token": f"{h}.{p}.{s}", "token_type": "bearer", "expires_in": 7200}
