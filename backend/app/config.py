"""
FastAPI 应用配置
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List


# app 所在目录 = backend/app/,项目根 = backend/
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


@dataclass
class Settings:
    APP_NAME: str = "股票数据库管理系统"
    APP_VERSION: str = "1.0.0"

    # JWT
    SECRET_KEY: str = os.environ.get(
        "STOCK_SECRET_KEY",
        "stock-admin-secret-change-me-in-prod-2026",
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = _int_env(
        "STOCK_TOKEN_EXPIRE_MINUTES", 60 * 12
    )

    # 默认管理员
    DEFAULT_ADMIN_USERNAME: str = os.environ.get("STOCK_ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD: str = os.environ.get("STOCK_ADMIN_PASSWORD", "admin123")

    # CORS
    CORS_ORIGINS: List[str] = field(
        default_factory=lambda: _split_env(
            "STOCK_CORS_ORIGINS",
            "*",
        )
    )

    # 服务
    HOST: str = os.environ.get("STOCK_HOST", "0.0.0.0")
    PORT: int = _int_env("STOCK_PORT", 8000)

    # 路径
    # 前端构建产物目录 (Vite build 输出到 frontend/dist/)
    FRONTEND_DIR: Path = BACKEND_ROOT.parent / "frontend" / "dist"
    DB_PATH: Path = BACKEND_ROOT / "data" / "stock.db"
    LOG_DIR: Path = BACKEND_ROOT / "logs"

    # 并发
    MAX_WORKERS: int = _int_env("STOCK_MAX_WORKERS", 8)


settings = Settings()