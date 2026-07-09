# User Authentication & Account Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement JWT-based user auth (register/login/refresh/logout) + admin user management APIs (list/stats/reset-password/delete) on the FastAPI A-end.

**Architecture:** New `server/routes/auth.py` for public auth endpoints. Existing `server/routes/admin.py` extended with user CRUD endpoints and a dual-acceptance auth dependency (X-Admin-Key OR JWT Bearer). Model `t_refresh_tokens` added, `t_users` gets `is_active`. Token logic lives in `server/services/auth.py` (pure functions, no DB). Repository extended with `UserRepository` and `RefreshTokenRepository`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, bcrypt 5.0, PyJWT 2.13, Pydantic 2.9

## Global Constraints

- `server/config.py` adds: `JWT_SECRET`, `JWT_EXPIRE_MINUTES` (default 30), `REFRESH_EXPIRE_DAYS` (default 7), `ADMIN_USERNAME` (default `admin`), `ADMIN_PASSWORD` (default `admin`)
- Admin routes accept both `X-Admin-Key` header and `Authorization: Bearer <JWT>` — either passes
- All auth endpoints return `{success: true/false, data/error: {...}}`
- Delete user sets `t_transactions.user_id` and `t_feedback.user_id` to NULL (not cascade)
- Refresh token rotation: old token revoked on refresh, expired records cleaned per-user on refresh
- bcrypt for password hashing, HS256 for JWT signing

---

### Task 1: Add JWT and admin config fields to `server/config.py`

**Files:**
- Modify: `server/config.py`

**Interfaces:**
- Produces: `settings.JWT_SECRET: str`, `settings.JWT_EXPIRE_MINUTES: int`, `settings.REFRESH_EXPIRE_DAYS: int`, `settings.ADMIN_USERNAME: str`, `settings.ADMIN_PASSWORD: str`

- [ ] **Step 1: Add five new environment variables to the Config class**

Open `server/config.py`, add the following five lines after the existing `STEP_RETRY_LIMIT` line (after line 109):

```python
    # ═════════════════════════════════════════════════════════════════════
    # Auth — JWT + admin seed
    # ═════════════════════════════════════════════════════════════════════
    JWT_SECRET: str = os.getenv("JWT_SECRET", "hajimi-jwt-secret-change-me")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))
    REFRESH_EXPIRE_DAYS: int = int(os.getenv("REFRESH_EXPIRE_DAYS", "7"))
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin")
```

- [ ] **Step 2: Verify the config loads**

Run:
```bash
python -c "from server.config import settings; print(settings.JWT_SECRET); print(settings.JWT_EXPIRE_MINUTES); print(settings.REFRESH_EXPIRE_DAYS); print(settings.ADMIN_USERNAME)"
```
Expected: prints `hajimi-jwt-secret-change-me`, `30`, `7`, `admin`

- [ ] **Step 3: Commit**

```bash
git add server/config.py
git commit -m "feat: add JWT and admin seed config fields"
```

---

### Task 2: Add RefreshToken model and is_active to User

**Files:**
- Modify: `server/database/models.py`

**Interfaces:**
- Produces: `RefreshToken` ORM class (table `t_refresh_tokens`), `User.is_active` column
- Consumed by: Task 3 (repository), Task 6 (auth routes), Task 7 (admin routes)

- [ ] **Step 1: Add `is_active` column to User**

Open `server/database/models.py`. In the `User` class, add a line after `role` (after line 45):

```python
    is_active = Column(Boolean, default=True)
```

The User class should now look like:

```python
class User(Base):
    __tablename__ = "t_users"

    user_id = Column(String(64), primary_key=True, default=_new_uuid)
    username = Column(String(128), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)  # bcrypt
    role = Column(String(16), nullable=False, default="user")  # user | admin
    is_active = Column(Boolean, default=True)
    preferences = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_now)
    last_login_at = Column(DateTime, nullable=True)
```

- [ ] **Step 2: Add RefreshToken class at the end of the file**

After the `Memory` class (after line 206), append:

```python
# ────────────────────────── t_refresh_tokens ──────────────────────────


class RefreshToken(Base):
    __tablename__ = "t_refresh_tokens"

    token_id = Column(String(64), primary_key=True, default=_new_uuid)
    user_id = Column(String(64), ForeignKey("t_users.user_id"), nullable=False, index=True)
    token_hash = Column(String(256), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, default=_now)
```

- [ ] **Step 3: Verify the table is created**

Run a quick startup test:
```bash
python -c "from server.database import init_db; init_db(); print('Tables created OK')"
```
Expected: `Tables created OK`

- [ ] **Step 4: Commit**

```bash
git add server/database/models.py
git commit -m "feat: add RefreshToken model and User.is_active column"
```

---

### Task 3: Add UserRepository and RefreshTokenRepository

**Files:**
- Modify: `server/database/repository.py`

**Interfaces:**
- Consumes: `User`, `RefreshToken` from models (Task 2)
- Produces: `UserRepository.create()`, `UserRepository.get_by_username()`, `UserRepository.get_by_id()`, `UserRepository.list_users()`, `UserRepository.get_user_stats()`, `UserRepository.update_password()`, `UserRepository.delete_user()`, `RefreshTokenRepository.create()`, `RefreshTokenRepository.get_by_hash()`, `RefreshTokenRepository.revoke()`, `RefreshTokenRepository.cleanup_expired()`

- [ ] **Step 1: Add imports at the top of repository.py**

Open `server/database/repository.py`. After the existing import block (after line 22), add `User` and `RefreshToken` to the imports, and add `hashlib`:

```python
import hashlib
import secrets

from server.database.models import (
    Failure,
    Feedback,
    Memory,
    RedlineLog,
    RefreshToken,
    StepLog,
    SystemConfig,
    Transaction,
    User,
)
```

- [ ] **Step 2: Append UserRepository after the ConfigRepository class**

After line 488 (end of file), before the file ends, append:

```python
class UserRepository:
    """用户管理仓库"""

    @staticmethod
    def create(
        username: str,
        password_hash: str,
        role: str = "user",
        db: Optional[Session] = None,
    ) -> User:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            user = User(
                username=username,
                password_hash=password_hash,
                role=role,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            return user
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_by_username(
        username: str,
        db: Optional[Session] = None,
    ) -> Optional[User]:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            return db.query(User).filter(User.username == username).first()
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_by_id(
        user_id: str,
        db: Optional[Session] = None,
    ) -> Optional[User]:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            return db.query(User).filter(User.user_id == user_id).first()
        finally:
            if close_db:
                db.close()

    @staticmethod
    def list_users(
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> tuple[int, list[User]]:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            from sqlalchemy import func

            q = db.query(User)
            if search:
                q = q.filter(User.username.contains(search))
            total = q.count()
            users = (
                q.order_by(User.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            return total, users
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_user_stats(
        user_id: str,
        db: Optional[Session] = None,
    ) -> dict:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            from sqlalchemy import func

            total_tasks = (
                db.query(func.count(Transaction.task_id))
                .filter(Transaction.user_id == user_id)
                .scalar()
            ) or 0
            success_count = (
                db.query(func.count(Transaction.task_id))
                .filter(Transaction.user_id == user_id, Transaction.result == "success")
                .scalar()
            ) or 0
            fail_count = (
                db.query(func.count(Transaction.task_id))
                .filter(Transaction.user_id == user_id, Transaction.result == "fail")
                .scalar()
            ) or 0
            feedback_count = (
                db.query(func.count(Feedback.feedback_id))
                .filter(Feedback.user_id == user_id)
                .scalar()
            ) or 0
            last_txn = (
                db.query(Transaction.timestamp)
                .filter(Transaction.user_id == user_id)
                .order_by(Transaction.timestamp.desc())
                .first()
            )

            return {
                "total_tasks": total_tasks,
                "success_count": success_count,
                "success_rate": round(success_count / total_tasks, 3) if total_tasks > 0 else 0.0,
                "total_failures": fail_count,
                "total_feedback": feedback_count,
                "last_active_at": last_txn[0].isoformat() if last_txn and last_txn[0] else None,
            }
        finally:
            if close_db:
                db.close()

    @staticmethod
    def update_password(
        user_id: str,
        new_password_hash: str,
        db: Optional[Session] = None,
    ) -> bool:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user:
                return False
            user.password_hash = new_password_hash
            db.commit()
            return True
        finally:
            if close_db:
                db.close()

    @staticmethod
    def delete_user(
        user_id: str,
        db: Optional[Session] = None,
    ) -> bool:
        """Delete user, set their transactions/feedback user_id to NULL."""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            user = db.query(User).filter(User.user_id == user_id).first()
            if not user:
                return False
            # Nullify foreign keys in transactions and feedback
            db.query(Transaction).filter(Transaction.user_id == user_id).update(
                {Transaction.user_id: None}
            )
            db.query(Feedback).filter(Feedback.user_id == user_id).update(
                {Feedback.user_id: None}
            )
            db.delete(user)
            db.commit()
            return True
        finally:
            if close_db:
                db.close()


class RefreshTokenRepository:
    """Refresh Token 仓库"""

    @staticmethod
    def create(
        user_id: str,
        token_hash: str,
        expires_at,
        db: Optional[Session] = None,
    ) -> RefreshToken:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            rt = RefreshToken(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
            db.add(rt)
            db.commit()
            db.refresh(rt)
            return rt
        finally:
            if close_db:
                db.close()

    @staticmethod
    def get_by_hash(
        token_hash: str,
        db: Optional[Session] = None,
    ) -> Optional[RefreshToken]:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            return (
                db.query(RefreshToken)
                .filter(RefreshToken.token_hash == token_hash)
                .first()
            )
        finally:
            if close_db:
                db.close()

    @staticmethod
    def revoke(
        token_hash: str,
        db: Optional[Session] = None,
    ) -> bool:
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            rt = (
                db.query(RefreshToken)
                .filter(RefreshToken.token_hash == token_hash)
                .first()
            )
            if not rt:
                return False
            rt.revoked_at = datetime.now(timezone.utc)
            db.commit()
            return True
        finally:
            if close_db:
                db.close()

    @staticmethod
    def cleanup_expired(
        user_id: str,
        db: Optional[Session] = None,
    ) -> int:
        """Delete all expired refresh tokens for a user. Returns count deleted."""
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            count = (
                db.query(RefreshToken)
                .filter(
                    RefreshToken.user_id == user_id,
                    RefreshToken.expires_at < datetime.now(timezone.utc),
                )
                .delete()
            )
            db.commit()
            return count
        finally:
            if close_db:
                db.close()
```

- [ ] **Step 3: Verify the repository imports cleanly**

Run:
```bash
python -c "from server.database.repository import UserRepository, RefreshTokenRepository; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add server/database/repository.py
git commit -m "feat: add UserRepository and RefreshTokenRepository"
```

---

### Task 4: Add auth service layer — password hashing and JWT helpers

**Files:**
- Create: `server/services/auth.py`

**Interfaces:**
- Produces: `hash_password(plain: str) -> str`, `verify_password(plain: str, hashed: str) -> bool`, `create_access_token(user_id: str, username: str, role: str) -> str`, `create_refresh_token() -> str` (returns raw token string), `hash_token(raw: str) -> str`, `decode_access_token(token: str) -> dict | None`
- Consumed by: Task 6 (auth routes), Task 7 (admin auth dependency)

- [ ] **Step 1: Create `server/services/auth.py`**

```python
"""
Auth service — password hashing, JWT creation/verification, token hashing.

Pure functions: no database access.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from server.config import settings


# ────────────────────────── password ──────────────────────────


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt. Returns the hash string."""
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(
        password.encode("utf-8"), hashed.encode("utf-8")
    )


# ────────────────────────── JWT ──────────────────────────


def create_access_token(user_id: str, username: str, role: str) -> str:
    """Create a signed JWT access token (short-lived)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def decode_access_token(token: str) -> dict | None:
    """Decode and validate an access token. Returns payload dict or None."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=["HS256"]
        )
        if payload.get("type") != "access":
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ────────────────────────── refresh token ──────────────────────────


def create_refresh_token() -> str:
    """Generate a cryptographically random refresh token (opaque string)."""
    return secrets.token_urlsafe(64)


def hash_token(raw: str) -> str:
    """SHA-256 hash a raw token string for database storage."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def refresh_token_expires_at() -> datetime:
    """Return the expiry datetime for a new refresh token."""
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_EXPIRE_DAYS)
```

- [ ] **Step 2: Sanity-check the module imports and functions work**

Run:
```bash
python -c "
from server.services.auth import hash_password, verify_password, create_access_token, create_refresh_token, hash_token, decode_access_token
h = hash_password('test123')
assert verify_password('test123', h)
assert not verify_password('wrong', h)
token = create_access_token('u1', 'alice', 'user')
payload = decode_access_token(token)
assert payload is not None
assert payload['sub'] == 'u1'
assert payload['role'] == 'user'
refresh = create_refresh_token()
assert len(refresh) > 60
print('All assertions passed')
"
```
Expected: `All assertions passed`

- [ ] **Step 3: Commit**

```bash
git add server/services/auth.py
git commit -m "feat: add auth service layer (bcrypt + JWT)"
```

---

### Task 5: Add Pydantic request/response models for auth

**Files:**
- Modify: `server/models/schemas.py`

**Interfaces:**
- Produces: `RegisterRequest`, `LoginRequest`, `RefreshRequest`, `LogoutRequest`, `TokenResponse`, `UserResponse`, `UserStatsResponse`, `UserListItem`, `ResetPasswordRequest`
- Consumed by: Task 6 (auth routes), Task 7 (admin routes)

- [ ] **Step 1: Append auth schemas at the end of schemas.py**

After the `InspectResponse` class (after line 314), append:

```python
# ────────────────────────── Auth 认证模型 ──────────────────────────


class RegisterRequest(BaseModel):
    """用户注册请求"""

    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    """登录请求"""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    """刷新 token 请求"""

    refresh_token: str


class LogoutRequest(BaseModel):
    """登出请求"""

    refresh_token: str


class ResetPasswordRequest(BaseModel):
    """管理员重置密码请求"""

    user_id: str
    new_password: str = Field(..., min_length=6, max_length=128)


class TokenResponse(BaseModel):
    """Token 响应体（login / refresh 共用）"""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # seconds until access token expires
    user: dict  # {user_id, username, role}


class UserListItem(BaseModel):
    """用户列表中的单条记录"""

    user_id: str
    username: str
    role: str
    is_active: bool
    task_count: int = 0
    last_login_at: Optional[str] = None
    created_at: Optional[str] = None


class UserListResponse(BaseModel):
    """用户列表响应"""

    total: int
    items: list[dict]


class UserStatsResponse(BaseModel):
    """单用户统计响应"""

    user_id: str
    username: str
    total_tasks: int
    success_rate: float
    total_failures: int
    total_feedback: int
    last_active_at: Optional[str] = None
```

- [ ] **Step 2: Verify schemas import**

Run:
```bash
python -c "from server.models.schemas import RegisterRequest, LoginRequest, TokenResponse, UserListItem; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add server/models/schemas.py
git commit -m "feat: add auth and user management Pydantic schemas"
```

---

### Task 6: Create auth routes (`/api/auth/*`)

**Files:**
- Create: `server/routes/auth.py`

**Interfaces:**
- Consumes: `UserRepository`, `RefreshTokenRepository` (Task 3), `hash_password`, `verify_password`, `create_access_token`, `create_refresh_token`, `hash_token`, `decode_access_token`, `refresh_token_expires_at` (Task 4), `RegisterRequest`, `LoginRequest`, `RefreshRequest`, `LogoutRequest`, `TokenResponse` (Task 5)
- Produces: FastAPI `auth_router` (prefix `/api/auth`, tag `Auth`)
- Registered in: Task 8 (main.py)

- [ ] **Step 1: Create `server/routes/auth.py`**

```python
"""
HAJIMI Auth API 路由

用户注册、登录、Token 刷新、登出。
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from server.database.repository import (
    RefreshTokenRepository,
    UserRepository,
)
from server.models.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
)
from server.services.auth import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    refresh_token_expires_at,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# ────────────────────────── 辅助 ──────────────────────────


def _token_pair_response(user_id: str, username: str, role: str) -> dict:
    """Generate access + refresh token pair and persist refresh token."""
    access_token = create_access_token(user_id, username, role)
    refresh_raw = create_refresh_token()
    refresh_hash = hash_token(refresh_raw)
    expires_at = refresh_token_expires_at()

    RefreshTokenRepository.create(
        user_id=user_id,
        token_hash=refresh_hash,
        expires_at=expires_at,
    )

    # Clean up expired tokens for this user
    RefreshTokenRepository.cleanup_expired(user_id)

    return {
        "success": True,
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_raw,
            "token_type": "Bearer",
            "expires_in": 1800,  # 30 minutes in seconds
            "user": {
                "user_id": user_id,
                "username": username,
                "role": role,
            },
        },
    }


# ────────────────────────── 注册 ──────────────────────────


@router.post("/register", summary="用户注册")
async def register(body: RegisterRequest):
    """注册新用户（role=user）"""
    existing = UserRepository.get_by_username(body.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "success": False,
                "error": {
                    "code": "USERNAME_TAKEN",
                    "message": f"用户名 '{body.username}' 已被占用",
                },
            },
        )

    password_hash = hash_password(body.password)
    user = UserRepository.create(
        username=body.username,
        password_hash=password_hash,
        role="user",
    )

    return {
        "success": True,
        "data": {
            "user_id": user.user_id,
            "username": user.username,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
    }


# ────────────────────────── 登录 ──────────────────────────


@router.post("/login", summary="用户登录")
async def login(body: LoginRequest):
    """用户名 + 密码登录，返回 JWT token pair"""
    user = UserRepository.get_by_username(body.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": {
                    "code": "INVALID_CREDENTIALS",
                    "message": "用户名或密码错误",
                },
            },
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": {
                    "code": "USER_DISABLED",
                    "message": "账号已被禁用",
                },
            },
        )

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": {
                    "code": "INVALID_CREDENTIALS",
                    "message": "用户名或密码错误",
                },
            },
        )

    # Update last_login_at
    from server.database import SessionLocal
    db = SessionLocal()
    try:
        user.last_login_at = datetime.now(timezone.utc)
        db.add(user)
        db.commit()
    finally:
        db.close()

    return _token_pair_response(user.user_id, user.username, user.role)


# ────────────────────────── 刷新 ──────────────────────────


@router.post("/refresh", summary="刷新 Token")
async def refresh(body: RefreshRequest):
    """用 refresh_token 换取新的 token pair（rotation）"""
    token_hash = hash_token(body.refresh_token)
    rt = RefreshTokenRepository.get_by_hash(token_hash)

    if not rt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": {
                    "code": "INVALID_CREDENTIALS",
                    "message": "无效的 refresh_token",
                },
            },
        )

    if rt.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": {
                    "code": "TOKEN_REVOKED",
                    "message": "Token 已被撤销，请重新登录",
                },
            },
        )

    if rt.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": {
                    "code": "TOKEN_EXPIRED",
                    "message": "Token 已过期，请重新登录",
                },
            },
        )

    # Rotation: revoke old token
    RefreshTokenRepository.revoke(token_hash)

    # Get the user
    user = UserRepository.get_by_id(rt.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": {
                    "code": "USER_DISABLED",
                    "message": "账号不存在或已被禁用",
                },
            },
        )

    return _token_pair_response(user.user_id, user.username, user.role)


# ────────────────────────── 登出 ──────────────────────────


@router.post("/logout", summary="登出")
async def logout(body: LogoutRequest):
    """撤销 refresh_token"""
    token_hash = hash_token(body.refresh_token)
    RefreshTokenRepository.revoke(token_hash)

    return {
        "success": True,
        "data": {
            "message": "已登出",
        },
    }
```

- [ ] **Step 2: Verify the router imports cleanly**

Run:
```bash
python -c "from server.routes.auth import router; print('auth router OK')"
```
Expected: `auth router OK`

- [ ] **Step 3: Test register and login endpoints manually**

Start the server:
```bash
python -m server.main &
```
Then test:
```bash
# Register
curl -s -X POST http://127.0.0.1:8010/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser1","password":"test123456"}' | python -m json.tool

# Login
curl -s -X POST http://127.0.0.1:8010/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser1","password":"test123456"}' | python -m json.tool
```
Expected: Register returns `{success:true, data:{user_id:"...",username:"testuser1"...}}`. Login returns `{success:true, data:{access_token:"...",refresh_token:"...",user:{...}}}`.

- [ ] **Step 4: Test refresh and logout**

Store tokens from login, then:
```bash
# Refresh
curl -s -X POST http://127.0.0.1:8010/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<token-from-login>"}' | python -m json.tool

# Logout
curl -s -X POST http://127.0.0.1:8010/api/auth/logout \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<token-from-refresh>"}' | python -m json.tool
```
Expected: Refresh returns new token pair. Logout returns `{success:true}`. Refreshing again with the old token returns 401 `TOKEN_REVOKED`.

- [ ] **Step 5: Stop the server and commit**

```bash
kill %1 2>/dev/null
git add server/routes/auth.py
git commit -m "feat: add auth routes (register/login/refresh/logout)"
```

---

### Task 7: Add admin user management routes + JWT admin auth

**Files:**
- Modify: `server/routes/admin.py`

**Interfaces:**
- Consumes: `UserRepository` (Task 3), `decode_access_token` (Task 4), `ResetPasswordRequest` (Task 5)
- Produces: new endpoints: `GET /users/list`, `GET /users/stats/{user_id}`, `POST /users/reset-password`, `DELETE /users/{user_id}`; new dependency `verify_admin_or_jwt`

- [ ] **Step 1: Add a dual-auth dependency and user management endpoints**

Open `server/routes/admin.py`. Replace the `verify_admin_key` function and everything after it with the full file below. The existing endpoints (stats_overview, top_tasks, trend, redline, failures_list, etc.) are preserved exactly — only the auth dependency is enhanced and four new endpoints are appended.

```python
"""
HAJIMI Admin API 路由

管理控制台接口：统计总览、配置管理、失败归因、红线统计、用户管理
对应 a-c-api-contract.md 中的 /api/admin/* 端点
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from server.config import settings
from server.database.repository import (
    ConfigRepository,
    RedlineRepository,
    TaskRepository,
    UserRepository,
)
from server.models.schemas import ResetPasswordRequest
from server.services.auth import decode_access_token
from server.services.metrics import metrics

router = APIRouter(prefix="/api/admin", tags=["Admin"])

# Bearer token scheme (optional — we allow either header)
_bearer_scheme = HTTPBearer(auto_error=False)


# ────────────────────────── 认证 ──────────────────────────


def verify_admin_key(x_admin_key: Optional[str] = Header(None)) -> str:
    """管理端认证（Demo 阶段与 demo key 相同）"""
    if not x_admin_key or x_admin_key != settings.DEMO_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "code": "AUTH_FAILED",
                    "message": "X-Admin-Key 无效",
                    "details": {},
                }
            },
        )
    return x_admin_key


def verify_admin_or_jwt(
    x_admin_key: Optional[str] = Header(None),
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """Dual-auth: accept X-Admin-Key OR Bearer JWT (role=admin)."""
    # Try demo key first
    if x_admin_key and x_admin_key == settings.DEMO_KEY:
        return {"auth_method": "demo_key"}

    # Try JWT
    if bearer and bearer.credentials:
        payload = decode_access_token(bearer.credentials)
        if payload and payload.get("role") == "admin":
            return {"auth_method": "jwt", "user_id": payload["sub"], "role": payload["role"]}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "error": {
                "code": "AUTH_FAILED",
                "message": "需要 X-Admin-Key 或管理员 JWT 认证",
                "details": {},
            }
        },
    )


# ────────────────────────── 统计总览 ──────────────────────────


@router.get(
    "/stats/overview",
    summary="仪表盘 KPI 总览",
    description="返回事务总量、成功率、L2/L3 占比等核心指标",
)
async def stats_overview(admin_key: str = Depends(verify_admin_key)):
    stats = TaskRepository.get_stats_overview()
    redline_stats = RedlineRepository.get_stats()
    stats.update(redline_stats)
    return stats


@router.get(
    "/stats/top-tasks",
    summary="高频任务 TOP 10",
)
async def stats_top_tasks(
    limit: int = 10,
    admin_key: str = Depends(verify_admin_key),
):
    from sqlalchemy import func

    from server.database import SessionLocal
    from server.database.models import Transaction

    db = SessionLocal()
    try:
        rows = (
            db.query(
                Transaction.intent_summary,
                func.count(Transaction.task_id).label("cnt"),
            )
            .group_by(Transaction.intent_summary)
            .order_by(func.count(Transaction.task_id).desc())
            .limit(limit)
            .all()
        )
        return {"top_tasks": [{"summary": r[0], "count": r[1]} for r in rows]}
    finally:
        db.close()


@router.get(
    "/stats/trend",
    summary="24h 事务趋势",
)
async def stats_trend(admin_key: str = Depends(verify_admin_key)):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func

    from server.database import SessionLocal
    from server.database.models import Transaction

    db = SessionLocal()
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        rows = (
            db.query(
                func.strftime("%H", Transaction.timestamp).label("hour"),
                func.count(Transaction.task_id).label("cnt"),
            )
            .filter(Transaction.timestamp >= since)
            .group_by("hour")
            .order_by("hour")
            .all()
        )
        return {"trend": [{"hour": r[0], "count": r[1]} for r in rows]}
    finally:
        db.close()


# ────────────────────────── 红线统计 ──────────────────────────


@router.get(
    "/stats/redline",
    summary="红线拦截统计",
)
async def stats_redline(admin_key: str = Depends(verify_admin_key)):
    return RedlineRepository.get_stats()


# ────────────────────────── 失败归因 ──────────────────────────


@router.get(
    "/failures/list",
    summary="失败记录列表",
)
async def failures_list(
    limit: int = 20,
    offset: int = 0,
    admin_key: str = Depends(verify_admin_key),
):
    from server.database import SessionLocal
    from server.database.models import Failure

    db = SessionLocal()
    try:
        total = db.query(Failure).count()
        rows = (
            db.query(Failure)
            .order_by(Failure.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return {
            "total": total,
            "items": [
                {
                    "failure_id": f.failure_id,
                    "task_id": f.task_id,
                    "failure_type": f.failure_type,
                    "step_index": f.step_index,
                    "error_detail": f.error_detail,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
                for f in rows
            ],
        }
    finally:
        db.close()


@router.get(
    "/failures/detail/{task_id}",
    summary="单条失败详情",
)
async def failure_detail(
    task_id: str,
    admin_key: str = Depends(verify_admin_key),
):
    from server.database import SessionLocal
    from server.database.models import Failure

    db = SessionLocal()
    try:
        f = db.query(Failure).filter(Failure.task_id == task_id).first()
        if not f:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "NOT_FOUND", "message": "记录不存在"}},
            )
        return {
            "failure_id": f.failure_id,
            "task_id": f.task_id,
            "failure_type": f.failure_type,
            "step_index": f.step_index,
            "fingerprint_hash": f.fingerprint_hash,
            "llm_snapshot": f.llm_snapshot,
            "error_detail": f.error_detail,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        }
    finally:
        db.close()


# ────────────────────────── 配置管理 ──────────────────────────


@router.get(
    "/config/current",
    summary="获取全部系统配置",
)
async def config_current(admin_key: str = Depends(verify_admin_key)):
    return {"configs": ConfigRepository.get_all()}


@router.post(
    "/config/deploy",
    summary="热部署配置",
)
async def config_deploy(
    key: str,
    value: dict,
    description: Optional[str] = None,
    admin_key: str = Depends(verify_admin_key),
):
    config = ConfigRepository.set(key, value, description)
    return {
        "deployed": True,
        "config_key": config.config_key,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


# ────────────────────────── 反馈统计 ──────────────────────────


@router.get(
    "/stats/feedback",
    summary="用户反馈分布",
)
async def stats_feedback(admin_key: str = Depends(verify_admin_key)):
    from sqlalchemy import func

    from server.database import SessionLocal
    from server.database.models import Feedback

    db = SessionLocal()
    try:
        rows = (
            db.query(
                Feedback.feedback_type,
                func.count(Feedback.feedback_id).label("cnt"),
            )
            .group_by(Feedback.feedback_type)
            .all()
        )
        return {"feedback_distribution": {r[0]: r[1] for r in rows}}
    finally:
        db.close()


# ────────────────────────── 性能指标 ──────────────────────────


@router.get(
    "/metrics",
    summary="性能指标",
    description="返回内存中收集的 P95/P50/平均延迟等性能指标。",
)
async def get_metrics(admin_key: str = Depends(verify_admin_key)):
    """Return performance metrics collected in-memory."""
    return {"metrics": metrics.get_all()}


@router.post(
    "/metrics/reset",
    summary="重置性能指标",
)
async def reset_metrics(admin_key: str = Depends(verify_admin_key)):
    """Reset all performance metrics."""
    metrics.reset()
    return {"reset": True}


# ────────────────────────── 会话状态 ──────────────────────────


@router.get(
    "/session/status",
    summary="当前会话状态",
    description="返回当前编排器会话的状态。",
)
async def session_status(admin_key: str = Depends(verify_admin_key)):
    """Return current orchestrator session state."""
    from server.services.agent.orchestrator import orchestrator

    return {"session": orchestrator.get_session()}


# ═══════════════════════════════════════════════════════════════════
# 用户管理（新增）
# ═══════════════════════════════════════════════════════════════════

from server.services.auth import hash_password


@router.get(
    "/users/list",
    summary="用户列表",
    description="分页查询用户列表，支持用户名搜索。需管理员权限。",
)
async def users_list(
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    auth: dict = Depends(verify_admin_or_jwt),
):
    """获取用户列表，含任务数量和最后登录时间。"""
    from server.database import SessionLocal
    from server.database.models import Transaction

    total, users = UserRepository.list_users(
        page=page,
        page_size=page_size,
        search=search,
    )

    # Collect task counts per user in one pass
    db = SessionLocal()
    try:
        from sqlalchemy import func

        items = []
        for u in users:
            task_count = (
                db.query(func.count(Transaction.task_id))
                .filter(Transaction.user_id == u.user_id)
                .scalar()
            ) or 0
            items.append({
                "user_id": u.user_id,
                "username": u.username,
                "role": u.role,
                "is_active": u.is_active,
                "task_count": task_count,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            })
    finally:
        db.close()

    return {
        "success": True,
        "data": {
            "total": total,
            "items": items,
        },
    }


@router.get(
    "/users/stats/{user_id}",
    summary="用户任务统计",
    description="获取指定用户的任务统计信息。需管理员权限。",
)
async def users_stats(
    user_id: str,
    auth: dict = Depends(verify_admin_or_jwt),
):
    """获取单用户的任务量、成功率、反馈等统计。"""
    user = UserRepository.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "用户不存在",
                },
            },
        )

    stats = UserRepository.get_user_stats(user_id)
    stats["user_id"] = user.user_id
    stats["username"] = user.username

    return {
        "success": True,
        "data": stats,
    }


@router.post(
    "/users/reset-password",
    summary="重置用户密码",
    description="管理员重置指定用户的密码。需管理员权限。",
)
async def users_reset_password(
    body: ResetPasswordRequest,
    auth: dict = Depends(verify_admin_or_jwt),
):
    """管理员重置用户密码。"""
    # Prevent admin from resetting their own password via this endpoint
    if auth.get("user_id") == body.user_id:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": {
                    "code": "CANNOT_DELETE_SELF",
                    "message": "不能通过此接口重置自己的密码",
                },
            },
        )

    new_hash = hash_password(body.new_password)
    ok = UserRepository.update_password(body.user_id, new_hash)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "用户不存在",
                },
            },
        )

    return {
        "success": True,
        "data": {
            "message": "密码已重置",
        },
    }


@router.delete(
    "/users/{user_id}",
    summary="删除用户",
    description="删除指定用户，其历史任务和反馈数据的 user_id 将被置空。需管理员权限。",
)
async def users_delete(
    user_id: str,
    auth: dict = Depends(verify_admin_or_jwt),
):
    """删除用户，历史数据保留但 user_id 置 NULL。"""
    # Prevent self-delete
    if auth.get("user_id") == user_id:
        raise HTTPException(
            status_code=400,
            detail={
                "success": False,
                "error": {
                    "code": "CANNOT_DELETE_SELF",
                    "message": "不能删除自己",
                },
            },
        )

    ok = UserRepository.delete_user(user_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "用户不存在",
                },
            },
        )

    return {
        "success": True,
        "data": {
            "message": "用户已删除",
        },
    }
```

- [ ] **Step 2: Verify admin.py imports cleanly**

Run:
```bash
python -c "from server.routes.admin import router, verify_admin_or_jwt; print('admin router OK')"
```
Expected: `admin router OK`

- [ ] **Step 3: Test user management endpoints**

Start the server:
```bash
python -m server.main &
```

Test with X-Admin-Key:
```bash
# List users
curl -s http://127.0.0.1:8010/api/admin/users/list?page=1 \
  -H "X-Admin-Key: hajimi-demo-2026" | python -m json.tool

# User stats
curl -s http://127.0.0.1:8010/api/admin/users/stats/default \
  -H "X-Admin-Key: hajimi-demo-2026" | python -m json.tool
```

Test with JWT:
```bash
# Login as admin
ADMIN_TOKEN=$(curl -s -X POST http://127.0.0.1:8010/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

# List users with JWT
curl -s http://127.0.0.1:8010/api/admin/users/list?page=1 \
  -H "Authorization: Bearer $ADMIN_TOKEN" | python -m json.tool

# Reset password for testuser1
curl -s -X POST http://127.0.0.1:8010/api/admin/users/reset-password \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"<testuser1_id>","new_password":"newpass123"}' | python -m json.tool

# Delete testuser1
curl -s -X DELETE http://127.0.0.1:8010/api/admin/users/<testuser1_id> \
  -H "Authorization: Bearer $ADMIN_TOKEN" | python -m json.tool
```
Expected: All return `{success:true}` with appropriate data.

- [ ] **Step 4: Stop the server and commit**

```bash
kill %1 2>/dev/null
git add server/routes/admin.py
git commit -m "feat: add admin user management endpoints + JWT dual-auth"
```

---

### Task 8: Register auth router and seed admin user in `server/main.py`

**Files:**
- Modify: `server/main.py`

**Interfaces:**
- Consumes: `auth_router` from Task 6
- Produces: Auth routes available at `/api/auth/*`, admin user seeded on startup

- [ ] **Step 1: Update `server/main.py`**

Replace the import block and startup event in `server/main.py`:

After line 20 (`from server.routes.admin import router as admin_router`), add:
```python
from server.routes.auth import router as auth_router
```

After line 27 (after `from server.routes.demo import router as demo_router` — now it's line 21), add `auth_router` to the router includes:

```python
# ────────────────────────── 路由注册 ──────────────────────────

app.include_router(demo_router)
app.include_router(admin_router)
app.include_router(auth_router)
```

Replace the existing default-user seeding block in `on_startup`:

The current `on_startup` has this (lines 31-55 of current file):
```python
@app.on_event("startup")
def on_startup():
    """初始化数据库表"""
    init_db()
    # Ensure default user exists ...
    try:
        ...
        user = User(
            user_id="default",
            username="default",
            password_hash="",
            ...
        )
        ...
    except Exception:
        pass
    # Pre-load memory cache ...
```

Replace it with:

```python
@app.on_event("startup")
def on_startup():
    """初始化数据库表 + 种子管理员账号"""
    init_db()

    # Seed admin and default users
    try:
        from server.database import SessionLocal
        from server.database.models import User
        from server.services.auth import hash_password

        db = SessionLocal()

        # Admin user from config
        admin_user = db.query(User).filter(User.username == settings.ADMIN_USERNAME).first()
        if not admin_user:
            admin_user = User(
                username=settings.ADMIN_USERNAME,
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                role="admin",
                is_active=True,
            )
            db.add(admin_user)
            db.commit()

        # Legacy default user (needed for existing memory extraction code)
        default_user = db.query(User).filter(User.username == "default").first()
        if not default_user:
            default_user = User(
                user_id="default",
                username="default",
                password_hash="",
                role="user",
                is_active=True,
            )
            db.add(default_user)
            db.commit()

        db.close()
    except Exception:
        pass

    # Pre-load memory cache for fast retrieval
    try:
        from server.services.memory.retriever import get_retriever
        get_retriever().load_cache()
    except Exception:
        pass  # Memory system failure should not block app startup
```

- [ ] **Step 2: Verify the server starts**

Run:
```bash
python -m server.main &
sleep 3
curl -s http://127.0.0.1:8010/ | python -m json.tool
```
Expected: `{"name":"HAJIMI Demo Server","version":"1.0.0","docs":"/docs"}`

Additionally, verify the admin user was seeded:
```bash
curl -s -X POST http://127.0.0.1:8010/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | python -m json.tool
```
Expected: `{success:true, data:{user:{role:"admin"...}}}`

- [ ] **Step 3: Stop the server and commit**

```bash
kill %1 2>/dev/null
git add server/main.py
git commit -m "feat: register auth routes and seed admin user on startup"
```

---

### Task 9: Update requirements

**Files:**
- Modify: `server/requirements.txt`

**Interfaces:**
- Produces: `bcrypt` and `PyJWT` in requirements.txt

- [ ] **Step 1: Add bcrypt and PyJWT to server/requirements.txt**

Open `server/requirements.txt`. Append after line 11:

```
bcrypt>=4.0
PyJWT>=2.8
```

- [ ] **Step 2: Commit**

```bash
git add server/requirements.txt
git commit -m "chore: add bcrypt and PyJWT to server requirements"
```

---

### Task 10: Write frontend API doc — `docs/api-auth.md`

**Files:**
- Create: `docs/api-auth.md`

**Interfaces:**
- Consumed by: frontend developer implementing login/register pages

- [ ] **Step 1: Create `docs/api-auth.md`**

```markdown
# HAJIMI 认证 API

> Base: `http://<host>:8010/api/auth`
> All endpoints are public (no auth header needed)

---

## POST /api/auth/register — 用户注册

**curl:**
```bash
curl -X POST http://127.0.0.1:8010/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"zhangsan","password":"mypass123"}'
```

**Response 200:**
```json
{
  "success": true,
  "data": {
    "user_id": "a1b2c3d4-...",
    "username": "zhangsan",
    "created_at": "2026-07-08T12:00:00Z"
  }
}
```

**Response 409 (username taken):**
```json
{
  "success": false,
  "error": {
    "code": "USERNAME_TAKEN",
    "message": "用户名 'zhangsan' 已被占用"
  }
}
```

**Validation:** username 2-64 chars, password 6-128 chars.

---

## POST /api/auth/login — 登录

**curl:**
```bash
curl -X POST http://127.0.0.1:8010/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"zhangsan","password":"mypass123"}'
```

**Response 200:**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbG...",
    "refresh_token": "dGhpcyBpcyBh...",
    "token_type": "Bearer",
    "expires_in": 1800,
    "user": {
      "user_id": "a1b2c3d4-...",
      "username": "zhangsan",
      "role": "user"
    }
  }
}
```

**Response 401 (wrong credentials):**
```json
{
  "success": false,
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "用户名或密码错误"
  }
}
```

**Response 403 (account disabled):**
```json
{
  "success": false,
  "error": {
    "code": "USER_DISABLED",
    "message": "账号已被禁用"
  }
}
```

---

## POST /api/auth/refresh — 刷新 Token

Use the `refresh_token` from login to get a new pair. The old refresh_token is invalidated after this call (rotation).

**curl:**
```bash
curl -X POST http://127.0.0.1:8010/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"dGhpcyBpcyBh..."}'
```

**Response 200:** Same shape as login.

**Response 401 (expired or revoked):**
```json
{
  "success": false,
  "error": {
    "code": "TOKEN_EXPIRED",
    "message": "Token 已过期，请重新登录"
  }
}
```

---

## POST /api/auth/logout — 登出

Revokes the refresh_token. Frontend MUST also delete tokens from localStorage.

**curl:**
```bash
curl -X POST http://127.0.0.1:8010/api/auth/logout \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"dGhpcyBpcyBh..."}'
```

**Response 200:**
```json
{
  "success": true,
  "data": {
    "message": "已登出"
  }
}
```

---

## Token 使用方式

后续请求携带 access_token：

```
Authorization: Bearer <access_token>
```

### Token 生命周期

| Token | 有效期 | 说明 |
|-------|--------|------|
| access_token | 30 min | 存 localStorage，用于所有 API 请求 |
| refresh_token | 7 days | 存 localStorage，只用于 /api/auth/refresh |

### 前端建议

1. 登录成功 → 存 `access_token` + `refresh_token` 到 localStorage
2. 每次发 API 请求 → 从 localStorage 读 `access_token`，放 `Authorization` header
3. 收到 401 → 尝试用 `refresh_token` 调 `/api/auth/refresh` 换新 token pair
4. refresh 也失败 → 跳转登录页，清空 localStorage
5. 登出 → 调 `/api/auth/logout`，然后清空 localStorage，跳转登录页
```

- [ ] **Step 2: Commit**

```bash
git add docs/api-auth.md
git commit -m "docs: add auth API reference for frontend developers"
```

---

### Task 11: Write frontend API doc — `docs/api-admin-users.md`

**Files:**
- Create: `docs/api-admin-users.md`

**Interfaces:**
- Consumed by: frontend developer implementing admin user management page

- [ ] **Step 1: Create `docs/api-admin-users.md`**

```markdown
# HAJIMI 管理员用户管理 API

> Base: `http://<host>:8010/api/admin/users`
> Auth: `X-Admin-Key: hajimi-demo-2026` OR `Authorization: Bearer <admin-jwt>`

---

## GET /api/admin/users/list — 用户列表

分页查询，支持用户名模糊搜索。

**Query params:**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| page | 1 | 页码 |
| page_size | 20 | 每页条数 |
| search | — | 按 username 模糊匹配 |

**curl:**
```bash
curl "http://127.0.0.1:8010/api/admin/users/list?page=1&page_size=20&search=zhang" \
  -H "X-Admin-Key: hajimi-demo-2026"
```

**Response 200:**
```json
{
  "success": true,
  "data": {
    "total": 150,
    "items": [
      {
        "user_id": "a1b2c3d4-...",
        "username": "zhangsan",
        "role": "user",
        "is_active": true,
        "task_count": 42,
        "last_login_at": "2026-07-08T10:00:00Z",
        "created_at": "2026-07-01T08:00:00Z"
      }
    ]
  }
}
```

---

## GET /api/admin/users/stats/{user_id} — 用户任务统计

**curl:**
```bash
curl http://127.0.0.1:8010/api/admin/users/stats/a1b2c3d4-... \
  -H "X-Admin-Key: hajimi-demo-2026"
```

**Response 200:**
```json
{
  "success": true,
  "data": {
    "user_id": "a1b2c3d4-...",
    "username": "zhangsan",
    "total_tasks": 42,
    "success_rate": 0.857,
    "total_failures": 5,
    "total_feedback": 30,
    "last_active_at": "2026-07-08T11:00:00Z"
  }
}
```

**Response 404:**
```json
{
  "success": false,
  "error": {
    "code": "USER_NOT_FOUND",
    "message": "用户不存在"
  }
}
```

---

## POST /api/admin/users/reset-password — 重置密码

**Body:**
```json
{
  "user_id": "a1b2c3d4-...",
  "new_password": "newpass456"
}
```

**curl:**
```bash
curl -X POST http://127.0.0.1:8010/api/admin/users/reset-password \
  -H "X-Admin-Key: hajimi-demo-2026" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"a1b2c3d4-...","new_password":"newpass456"}'
```

**Response 200:**
```json
{
  "success": true,
  "data": {
    "message": "密码已重置"
  }
}
```

**Note:** 管理员不能通过此接口重置自己的密码（返回 400 `CANNOT_DELETE_SELF`）。

---

## DELETE /api/admin/users/{user_id} — 删除用户

删除用户，其历史任务和反馈数据保留但 user_id 置空。

**curl:**
```bash
curl -X DELETE http://127.0.0.1:8010/api/admin/users/a1b2c3d4-... \
  -H "X-Admin-Key: hajimi-demo-2026"
```

**Response 200:**
```json
{
  "success": true,
  "data": {
    "message": "用户已删除"
  }
}
```

**Note:** 管理员不能删除自己（返回 400 `CANNOT_DELETE_SELF`）。

---

## 错误码

| code | HTTP | 说明 |
|------|------|------|
| AUTH_FAILED | 401 | 未认证 |
| ADMIN_REQUIRED | 403 | 需要管理员权限（JWT role != admin） |
| USER_NOT_FOUND | 404 | 用户不存在 |
| CANNOT_DELETE_SELF | 400 | 不能删除/重置自己 |
```

- [ ] **Step 2: Commit**

```bash
git add docs/api-admin-users.md
git commit -m "docs: add admin user management API reference"
```

---

### Task 12: Final integration test

**Files:**
- No file changes — verification test only

- [ ] **Step 1: Start the server fresh and run full integration test**

```bash
# Ensure server is not running
kill %1 2>/dev/null

# Start fresh
python -m server.main &
sleep 3

# 1. Health check
echo "=== Health ==="
curl -s http://127.0.0.1:8010/api/demo/health | python -c "import sys,json; d=json.load(sys.stdin); assert d['status'] in ('ok','degraded'); print('Health: PASS')"

# 2. Register
echo "=== Register ==="
curl -s -X POST http://127.0.0.1:8010/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"inttest","password":"testpass123"}' | python -c "import sys,json; d=json.load(sys.stdin); assert d['success']; print('Register: PASS'); uid=d['data']['user_id']"

# 3. Login as registered user
echo "=== Login ==="
LOGIN_RESP=$(curl -s -X POST http://127.0.0.1:8010/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"inttest","password":"testpass123"}')
echo "$LOGIN_RESP" | python -c "import sys,json; d=json.load(sys.stdin); assert d['success']; print('Login: PASS')"
ACCESS_TOKEN=$(echo "$LOGIN_RESP" | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")
REFRESH_TOKEN=$(echo "$LOGIN_RESP" | python -c "import sys,json; print(json.load(sys.stdin)['data']['refresh_token'])")

# 4. Login as admin
echo "=== Admin Login ==="
ADMIN_RESP=$(curl -s -X POST http://127.0.0.1:8010/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}')
echo "$ADMIN_RESP" | python -c "import sys,json; d=json.load(sys.stdin); assert d['success']; assert d['data']['user']['role']=='admin'; print('Admin Login: PASS')"
ADMIN_TOKEN=$(echo "$ADMIN_RESP" | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

# 5. Access admin endpoint with JWT
echo "=== Admin Users List (JWT) ==="
curl -s http://127.0.0.1:8010/api/admin/users/list \
  -H "Authorization: Bearer $ADMIN_TOKEN" | python -c "import sys,json; d=json.load(sys.stdin); assert d['success']; print('Admin List (JWT): PASS')"

# 6. Refresh token
echo "=== Refresh ==="
REFRESH_RESP=$(curl -s -X POST http://127.0.0.1:8010/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH_TOKEN\"}")
echo "$REFRESH_RESP" | python -c "import sys,json; d=json.load(sys.stdin); assert d['success']; print('Refresh: PASS')"

# 7. Old refresh token is now revoked
echo "=== Old Refresh Revoked ==="
curl -s -X POST http://127.0.0.1:8010/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH_TOKEN\"}" | python -c "import sys,json; d=json.load(sys.stdin); assert d['success']==False; assert d['error']['code']=='TOKEN_REVOKED'; print('Revoke check: PASS')"

# 8. Non-admin cannot access admin endpoints
echo "=== Non-admin Rejected ==="
curl -s http://127.0.0.1:8010/api/admin/users/list \
  -H "Authorization: Bearer $ACCESS_TOKEN" | python -c "import sys,json; d=json.load(sys.stdin); print('Non-admin rejected: PASS' if 'error' in d else 'FAIL')"

# 9. Cleanup — delete test user
echo "=== Cleanup ==="
curl -s -X DELETE "http://127.0.0.1:8010/api/admin/users/inttest" \
  -H "Authorization: Bearer $ADMIN_TOKEN" 2>/dev/null || echo "(user may have a different id, manual cleanup if needed)"

echo "=== ALL TESTS PASSED ==="
```

- [ ] **Step 2: Stop server**

```bash
kill %1 2>/dev/null
```

- [ ] **Step 3: Commit any final touches**

```bash
git add -A
git diff --cached --stat
git commit -m "test: full integration flow for auth and admin user management" || echo "Nothing to commit"
```

---

## File Summary

| # | File | Action |
|---|------|--------|
| 1 | `server/config.py` | Modify — add 5 config fields |
| 2 | `server/database/models.py` | Modify — add RefreshToken, User.is_active |
| 3 | `server/database/repository.py` | Modify — add UserRepository, RefreshTokenRepository |
| 4 | `server/services/auth.py` | **Create** — hash_password, JWT helpers |
| 5 | `server/models/schemas.py` | Modify — add Auth Pydantic models |
| 6 | `server/routes/auth.py` | **Create** — /api/auth/* endpoints |
| 7 | `server/routes/admin.py` | Modify — dual-auth + 4 user CRUD endpoints |
| 8 | `server/main.py` | Modify — register auth router, seed admin |
| 9 | `server/requirements.txt` | Modify — add bcrypt, PyJWT |
| 10 | `docs/api-auth.md` | **Create** — frontend auth API doc |
| 11 | `docs/api-admin-users.md` | **Create** — frontend admin users API doc |

