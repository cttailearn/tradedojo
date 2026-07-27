"""
数据库封装 —— 复用 backend/db/database.py 的 SQLite 连接
外加 admin 用户表 + 训练相关表 CRUD

P0 安全加固:
- 不再 print 默认管理员密码
- 默认密码仅在 STOCK_DEV=1 且密码未提供时,使用一个强随机临时密码并写日志(不打印)
- 生产环境未设置 STOCK_ADMIN_PASSWORD 时直接报错
"""
import logging
import sqlite3
import hashlib
import secrets
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from app.config import settings
from db.database import get_conn as _orig_get_conn  # noqa: F401  复用


log = logging.getLogger("app.auth")


# ---- 用户表初始化 ----
USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_user (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    is_active     INTEGER DEFAULT 1,
    must_change_pw INTEGER DEFAULT 0,  -- 1=下次登录必须改密
    created_at    TEXT DEFAULT (datetime('now', 'localtime')),
    last_login    TEXT,
    last_failed_login TEXT,
    failed_attempts INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_admin_username ON admin_user(username);
"""


def init_user_db():
    """初始化 admin_user 表(含 must_change_pw 列的在线 ALTER 兼容)"""
    with _orig_get_conn() as conn:
        conn.executescript(USER_SCHEMA)
        # 老库兼容:补列
        for col_def, col_name in (
            ("must_change_pw INTEGER DEFAULT 0", "must_change_pw"),
            ("last_failed_login TEXT", "last_failed_login"),
            ("failed_attempts INTEGER DEFAULT 0", "failed_attempts"),
        ):
            try:
                conn.execute(f"SELECT {col_name} FROM admin_user LIMIT 1")
            except Exception:
                conn.execute(f"ALTER TABLE admin_user ADD COLUMN {col_def}")


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


def create_user(
    username: str,
    password: str,
    *,
    must_change_pw: bool = False,
) -> dict:
    h, salt = hash_password(password)
    with _orig_get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO admin_user(username, password_hash, salt, must_change_pw) "
            "VALUES(?, ?, ?, ?)",
            (username, h, salt, 1 if must_change_pw else 0),
        )
        uid = cur.lastrowid
    return {"id": uid, "username": username}


def update_last_login(user_id: int):
    with _orig_get_conn() as conn:
        conn.execute(
            "UPDATE admin_user SET last_login = datetime('now', 'localtime'), "
            "failed_attempts = 0 WHERE id = ?",
            (user_id,),
        )


def record_failed_login(user_id: int):
    with _orig_get_conn() as conn:
        conn.execute(
            "UPDATE admin_user SET failed_attempts = failed_attempts + 1, "
            "last_failed_login = datetime('now', 'localtime') WHERE id = ?",
            (user_id,),
        )


def is_user_locked(user: dict, max_attempts: int = 5, window_minutes: int = 15) -> bool:
    """简单账户锁定:连续失败 >= max_attempts 且最近失败在 window 内。"""
    if (user.get("failed_attempts") or 0) < max_attempts:
        return False
    last = user.get("last_failed_login")
    if not last:
        return False
    try:
        from datetime import datetime, timedelta
        dt = datetime.fromisoformat(last)
        return datetime.now() - dt < timedelta(minutes=window_minutes)
    except Exception:
        return False


def ensure_default_admin():
    """确保存在默认管理员(生产不允许使用 admin/admin123)"""
    init_user_db()
    username = settings.DEFAULT_ADMIN_USERNAME
    user = get_user_by_username(username)

    if user is None:
        # 创建管理员时,密码来源:
        #   1) STOCK_ADMIN_PASSWORD 显式提供  → 直接使用
        #   2) STOCK_DEV=1            → 生成强随机临时密码,写日志(不打印)
        #   3) 其他情况                → 抛错,要求显式配置
        pwd = settings.DEFAULT_ADMIN_PASSWORD
        if not pwd:
            if not settings.is_dev:
                raise RuntimeError(
                    f"未设置 STOCK_ADMIN_PASSWORD 且管理员 {username} 不存在。"
                    "请设置 STOCK_ADMIN_PASSWORD 后再启动。"
                )
            pwd = secrets.token_urlsafe(24)
        # 必须改密标志:首登前永远要求改(防止 admin/admin123 类默认密码继续生效)
        create_user(
            username,
            pwd,
            must_change_pw=settings.REQUIRE_PASSWORD_CHANGE_ON_FIRST_LOGIN,
        )
        if settings.is_dev and not settings.DEFAULT_ADMIN_PASSWORD:
            # 仅 dev + 临时随机密码时,写一份到受保护的文件
            token_path = Path(settings.LOG_DIR) / "DEV_ADMIN_PASSWORD.txt"
            token_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                token_path.write_text(
                    f"username={username}\npassword={pwd}\n"
                    f"# 仅用于本地开发,生产请设置 STOCK_ADMIN_PASSWORD\n",
                    encoding="utf-8",
                )
                # 收紧权限(Windows 下尽量设置)
                try:
                    token_path.chmod(0o600)
                except Exception:
                    pass
                log.warning(
                    "[AUTH] dev 模式:已生成临时管理员密码,写入 %s (生产请显式设置 STOCK_ADMIN_PASSWORD)",
                    token_path,
                )
            except Exception as e:
                log.error("[AUTH] 写 dev 临时密码失败: %s", e)
        else:
            log.info("[AUTH] 已创建默认管理员账号: %s (生产已配置 STOCK_ADMIN_PASSWORD)", username)
    else:
        # 已存在: 标记强制改密(若配置要求)—— 这里不动老账号,避免误伤
        log.info("[AUTH] 默认管理员已存在: %s", username)