"""
HAJIMI Auth API 路由
======================
管理员登录，JWT 签发。
对应 a-c-api-contract.md §3.7 的 POST /api/auth/login 端点。
"""
import hashlib
import time
import json
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from server.config import settings
from server.database import SessionLocal
from server.database.models import User

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ── 请求模型 ──

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 7200
    refresh_token: str


# ── 路由 ──

@router.post("/login", summary="管理员登录")
async def login(request: LoginRequest):
    """管理员登录，返回 JWT access_token + refresh_token"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == request.username).first()

        if not user:
            # Demo 阶段：允许任意非空密码登录，自动创建用户
            if request.password:
                user = User(
                    username=request.username,
                    password_hash=_hash(request.password),
                    role="admin",
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            else:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"error": {"code": "AUTH_FAILED", "message": "用户名或密码错误", "details": {}}},
                )
        elif not _verify(request.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": {"code": "AUTH_FAILED", "message": "用户名或密码错误", "details": {}}},
            )
    finally:
        db.close()

    now = int(time.time())
    access_token = _make_jwt(user.username, "admin", now, 7200)     # 2h
    refresh_token = _make_jwt(user.username, "admin", now, 604800)  # 7d

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


# ── JWT 简易实现（Demo 阶段，生产环境用 python-jose）──

def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _verify(password: str, hash_hex: str) -> bool:
    return _hash(password) == hash_hex


def _make_jwt(username: str, role: str, now: int, expires_in: int) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + expires_in,
    }
    # Demo 阶段用简单的 base64 编码，非标准 JWS
    import base64
    h = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = hashlib.sha256(f"{h}.{p}.{settings.DEMO_KEY}".encode()).hexdigest()[:16]
    return f"{h}.{p}.{sig}"
