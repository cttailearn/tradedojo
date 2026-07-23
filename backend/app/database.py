"""
数据库封装 —— 复用 backend/db/database.py 的 SQLite 连接
外加 admin 用户表 + 训练相关表 CRUD
"""
import sqlite3
import hashlib
import secrets
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from app.config import settings
from db.database import get_conn as _orig_get_conn  # noqa: F401  复用


# ---- 用户表初始化 ----
USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_user (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    is_active     INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now', 'localtime')),
    last_login    TEXT
);
CREATE INDEX IF NOT EXISTS idx_admin_username ON admin_user(username);
"""


def init_user_db():
    """初始化 admin_user 表"""
    with _orig_get_conn() as conn:
        conn.executescript(USER_SCHEMA)


# ---- 密码哈希(使用 PBKDF2-SHA256,无需额外依赖) ----
def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"),
        salt.encode("utf-8"), 200_000
    )
    return h.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    h, _ = hash_password(password, salt)
    return secrets.compare_digest(h, password_hash)


# ---- 用户 CRUD ----
def get_user_by_username(username: str) -> Optional[dict]:
    with _orig_get_conn() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM admin_user WHERE username = ?", (username,)
        ).fetchone()
    return dict(row) if row else None


def create_user(username: str, password: str) -> dict:
    h, salt = hash_password(password)
    with _orig_get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO admin_user (username, password_hash, salt) VALUES (?, ?, ?)",
            (username, h, salt),
        )
        uid = cur.lastrowid
    return {"id": uid, "username": username}


def update_last_login(user_id: int):
    with _orig_get_conn() as conn:
        conn.execute(
            "UPDATE admin_user SET last_login = datetime('now', 'localtime') WHERE id = ?",
            (user_id,),
        )


def ensure_default_admin():
    """确保存在默认管理员"""
    init_user_db()
    username = settings.DEFAULT_ADMIN_USERNAME
    password = settings.DEFAULT_ADMIN_PASSWORD
    user = get_user_by_username(username)
    if user is None:
        create_user(username, password)
        print(f"[AUTH] 已创建默认管理员账号: {username} / {password}")
    else:
        print(f"[AUTH] 默认管理员已存在: {username}")