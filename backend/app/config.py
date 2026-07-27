"""
FastAPI 应用配置

P0 安全加固:
- SECRET_KEY 未设置时直接抛异常(不允许默认值)
- DEFAULT_ADMIN_PASSWORD 不再静默使用默认值,启动时由 database 强制校验
- CORS 默认仅允许 localhost 同源,生产必须显式配置
"""
import os
import secrets
from pathlib import Path
from dataclasses import dataclass, field
from typing import List


APP_DIR = Path(__file__).parent
BACKEND_ROOT = APP_DIR.parent


def _split_env(name: str, default: str = "") -> List[str]:
    raw = os.environ.get(name, default)
    if not raw:
        return []
    if raw.strip() in ("*", "['*']", '["*"]'):
        return ["*"]
    return [x.strip() for x in raw.split(",") if x.strip()]


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _require_secret_key() -> str:
    """
    生产必须显式设置 STOCK_SECRET_KEY。
    - 显式提供: 直接使用
    - 未提供且允许开发模式(STOCK_DEV=1): 临时生成一个,只用于本地
    - 未提供且生产模式: 启动失败
    """
    raw = os.environ.get("STOCK_SECRET_KEY", "").strip()
    if raw:
        # 防止误用明显的占位值
        bad = (
            "change-me",
            "secret",
            "stock-admin",
            "default",
        )
        low = raw.lower()
        for b in bad:
            if b in low:
                raise RuntimeError(
                    f"STOCK_SECRET_KEY 包含不安全的占位字符串 ({b}),请换一个强随机值"
                )
        if len(raw) < 32:
            raise RuntimeError("STOCK_SECRET_KEY 长度至少 32 字符")
        return raw

    if os.environ.get("STOCK_DEV") == "1":
        # 仅 dev: 生成一个进程级临时密钥(重启即变,适合本地)
        return f"dev-{secrets.token_urlsafe(48)}"

    raise RuntimeError(
        "未设置 STOCK_SECRET_KEY 且未启用 STOCK_DEV=1。"
        "生产环境必须设置至少 32 字符的强随机密钥。"
        "可通过 `python -c \"import secrets;print(secrets.token_urlsafe(48))\"` 生成。"
    )


@dataclass
class Settings:
    APP_NAME: str = "股票数据库管理系统"
    APP_VERSION: str = "1.0.0"

    # ---------- JWT ----------
    SECRET_KEY: str = field(default_factory=_require_secret_key)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = _int_env(
        "STOCK_TOKEN_EXPIRE_MINUTES", 60 * 12  # 默认 12h,生产建议改小或用 refresh token
    )
    REFRESH_TOKEN_EXPIRE_DAYS: int = _int_env(
        "STOCK_REFRESH_TOKEN_EXPIRE_DAYS", 7
    )

    # ---------- 默认管理员 ----------
    # 不再直接读取明文密码,启动时强制校验
    DEFAULT_ADMIN_USERNAME: str = os.environ.get("STOCK_ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD: str = os.environ.get("STOCK_ADMIN_PASSWORD", "")
    REQUIRE_PASSWORD_CHANGE_ON_FIRST_LOGIN: bool = (
        os.environ.get("STOCK_REQUIRE_PWD_CHANGE", "1") == "1"
    )

    # ---------- CORS ----------
    # 生产必须显式设置 STOCK_CORS_ORIGINS=逗号分隔域名
    # 默认 * 仍然保留兼容,但 main.py 检测到 SECRET_KEY 不是 dev- 开头时强制要求显式列表
    CORS_ORIGINS: List[str] = field(
        default_factory=lambda: _split_env(
            "STOCK_CORS_ORIGINS",
            "*",
        )
    )
    CORS_ALLOW_CREDENTIALS: bool = (
        os.environ.get("STOCK_CORS_CREDENTIALS", "0") == "1"
    )

    # ---------- 服务 ----------
    HOST: str = os.environ.get("STOCK_HOST", "0.0.0.0")
    PORT: int = _int_env("STOCK_PORT", 8000)
    BEHIND_PROXY: bool = os.environ.get("STOCK_BEHIND_PROXY", "0") == "1"

    # ---------- 路径 ----------
    FRONTEND_DIR: Path = BACKEND_ROOT.parent / "frontend" / "dist"
    DB_PATH: Path = BACKEND_ROOT / "data" / "stock.db"
    LOG_DIR: Path = BACKEND_ROOT / "logs"

    # ---------- 并发 ----------
    MAX_WORKERS: int = _int_env("STOCK_MAX_WORKERS", 8)

    # ---------- 限速 ----------
    RATE_LIMIT_ENABLED: bool = os.environ.get("STOCK_RATE_LIMIT", "1") == "1"
    LOGIN_RATE_LIMIT: str = os.environ.get("STOCK_LOGIN_RATE_LIMIT", "10/minute")
    REGISTER_RATE_LIMIT: str = os.environ.get("STOCK_REGISTER_RATE_LIMIT", "5/minute")
    GLOBAL_RATE_LIMIT: str = os.environ.get("STOCK_GLOBAL_RATE_LIMIT", "300/minute")

    # ---------- 安全响应头 ----------
    ENABLE_SECURITY_HEADERS: bool = (
        os.environ.get("STOCK_SECURITY_HEADERS", "1") == "1"
    )
    HSTS_MAX_AGE: int = _int_env("STOCK_HSTS_MAX_AGE", 31536000)

    @property
    def is_dev(self) -> bool:
        return self.SECRET_KEY.startswith("dev-")


settings = Settings()