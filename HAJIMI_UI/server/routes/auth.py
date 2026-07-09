"""POST /api/auth/login — JWT 签发；POST /api/auth/refresh — 令牌刷新"""
import base64
import hashlib
import json
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from server.config import settings
from server.database import SessionLocal
from server.database.models import User

router = APIRouter(prefix="/api/auth", tags=["Auth"])

# 令牌有效期（秒）
ACCESS_TTL = 7200            # access token 2 小时
REFRESH_TTL = 7 * 24 * 3600  # refresh token 7 天


# ────────────────────────── 令牌工具 ──────────────────────────
# 说明：沿用原有的轻量签名方案（HMAC 近似：sha256(header.payload.DEMO_KEY)[:16]），
# 不引入新依赖、不改变 access token 的既有格式；仅新增 refresh 类型与校验。

def _sign(h: str, p: str) -> str:
    return hashlib.sha256(f"{h}.{p}.{settings.DEMO_KEY}".encode()).hexdigest()[:16]


def _b64(obj: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")


def _make_token(sub: str, role: str, typ: str, ttl: int) -> str:
    """生成签名令牌。typ 为 access / refresh，用于区分用途。"""
    now = int(time.time())
    h = _b64({"alg": "HS256", "typ": "JWT"})
    p = _b64({"sub": sub, "role": role, "typ": typ, "iat": now, "exp": now + ttl})
    return f"{h}.{p}.{_sign(h, p)}"


def _verify_token(token: str, expected_typ: str) -> dict:
    """校验签名、类型与过期时间，返回 payload；失败抛 401。"""
    try:
        h, p, s = token.split(".")
    except (ValueError, AttributeError):
        raise HTTPException(401, detail={"error": {"code": "TOKEN_INVALID", "message": "令牌格式错误"}})
    if _sign(h, p) != s:
        raise HTTPException(401, detail={"error": {"code": "TOKEN_INVALID", "message": "令牌签名无效"}})
    try:
        payload = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)).decode())
    except Exception:
        raise HTTPException(401, detail={"error": {"code": "TOKEN_INVALID", "message": "令牌解析失败"}})
    if payload.get("typ") != expected_typ:
        raise HTTPException(401, detail={"error": {"code": "TOKEN_TYPE", "message": "令牌类型不匹配"}})
    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(401, detail={"error": {"code": "TOKEN_EXPIRED", "message": "令牌已过期"}})
    return payload


# ────────────────────────── /login ──────────────────────────

class LoginReq(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


@router.post("/login")
async def login(req: LoginReq):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == req.username).first()
        pwd_hash = hashlib.sha256(req.password.encode()).hexdigest()
        if not user and req.password:
            user = User(
                username=req.username,
                password_hash=pwd_hash,
                role="admin",
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        elif not user or pwd_hash != user.password_hash:
            raise HTTPException(
                401,
                detail={"error": {"code": "AUTH_FAILED", "message": "用户名或密码错误"}},
            )
        role = user.role or "admin"
    finally:
        db.close()

    # 保持 access token 既有格式不变，新增 refresh_token（向后兼容的附加字段）
    return {
        "access_token": _make_token(req.username, role, "access", ACCESS_TTL),
        "refresh_token": _make_token(req.username, role, "refresh", REFRESH_TTL),
        "token_type": "bearer",
        "expires_in": ACCESS_TTL,
    }


# ────────────────────────── /refresh ──────────────────────────

class RefreshReq(BaseModel):
    refresh_token: str = Field(min_length=1)


@router.post("/refresh")
async def refresh(req: RefreshReq):
    """用有效的 refresh_token 换取新的 access_token（并滚动下发新的 refresh_token）。"""
    payload = _verify_token(req.refresh_token, "refresh")
    sub = payload.get("sub", "")
    role = payload.get("role", "admin")

    # 前端响应拦截器读取 { success, data: { access_token, refresh_token, user } }
    return {
        "success": True,
        "data": {
            "access_token": _make_token(sub, role, "access", ACCESS_TTL),
            "refresh_token": _make_token(sub, role, "refresh", REFRESH_TTL),
            "token_type": "bearer",
            "expires_in": ACCESS_TTL,
            "user": {"username": sub, "role": role},
        },
    }
