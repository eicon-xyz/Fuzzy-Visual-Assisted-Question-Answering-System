"""
HAJIMI 数据库层 — SQLAlchemy 引擎与会话工厂

开发/演示阶段使用 SQLite，生产可切换 PostgreSQL。
"""

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from server.config import settings

# SQLite 数据库文件路径（项目根目录）
DB_PATH = Path(__file__).parent.parent.parent / "data" / "hajimi.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("HAJIMI_DATABASE_URL", f"sqlite:///{DB_PATH}")

# SQLite 引擎配置
_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=_connect_args,
)


# SQLite WAL 模式（更好的并发）
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI 依赖：获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有表（开发阶段使用，生产用 Alembic）"""
    import server.database.models  # noqa: F401 — 确保所有 ORM 模型已注册

    Base.metadata.create_all(bind=engine)
