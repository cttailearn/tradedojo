"""
FastAPI 主入口
- 启动时初始化数据库(库表 + 默认管理员)
- 注册 CORS / 安全响应头 / 限速 / 静态前端 / 路由
- 托管 Vite 构建产物 (frontend/dist/)

P0/P1 加固:
- CORS: 生产必须显式 STOCK_CORS_ORIGINS,allow_credentials 默认关闭
- 全局异常处理: 对外只暴露 error_id,详情进日志
- 安全响应头: HSTS / nosniff / frame deny / referrer
- 限速: slowapi 接入 /api/* 全局 + 登录/注册/兑换高频端点额外收紧
- HF_ENDPOINT: 默认 hf-mirror.com(国内友好)
"""
import os
import logging
import sys
import uuid
from pathlib import Path
from contextlib import asynccontextmanager

# HF_ENDPOINT 修复:默认走 hf-mirror(国内友好),env 可覆盖
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ---- 让 backend/ 下的模块可以绝对导入 ----
BACKEND_ROOT = Path(__file__).parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import settings
from app.database import ensure_default_admin, init_user_db
from app.exceptions import register_exception_handlers
from app.security_headers import SecurityHeadersMiddleware
from app.rate_limit import limiter, rate_limit_exceeded_handler
from db.database import init_db
from app.routers import (
    auth, stocks, kline, tasks, backtest, system,
    scheduler, sources, kronos,
    train, train_auth, train_admin, train_stats,
    train_indices,
)

from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

logger = logging.getLogger("app")


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ---- 启动 ----
        logger.info("[STARTUP] 初始化数据库 ...")
        init_db(verbose=False)
        init_user_db()
        ensure_default_admin()
        logger.info(
            "[STARTUP] 完成。前端目录: %s | SECRET_KEY is_dev=%s",
            settings.FRONTEND_DIR, settings.is_dev,
        )
        try:
            yield
        finally:
            # ---- 关闭 ----
            logger.info("[SHUTDOWN] 关闭 ...")

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="A 股数据库管理与回测系统",
        lifespan=lifespan,
    )

    # ---- 限速 (slowapi) ----
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ---- 安全响应头 ----
    if settings.ENABLE_SECURITY_HEADERS:
        app.add_middleware(SecurityHeadersMiddleware)

    # ---- CORS ----
    origins = settings.CORS_ORIGINS
    # 生产模式下若仍为 wildcard + credentials=1 是不合法组合,直接拒绝
    if not settings.is_dev:
        if "*" in origins and settings.CORS_ALLOW_CREDENTIALS:
            raise RuntimeError(
                "生产模式禁止 CORS allow_origins=['*'] + allow_credentials=True 的组合。"
                "请设置 STOCK_CORS_ORIGINS=具体域名,并按需 STOCK_CORS_CREDENTIALS=1"
            )
        if "*" in origins:
            logger.warning(
                "CORS 当前为 wildcard(*);生产请设置 STOCK_CORS_ORIGINS 为具体域名"
            )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "Origin",
            "X-Requested-With",
            "X-CSRF-Token",
        ],
        expose_headers=["X-Error-Id"],
        max_age=600,
    )

    # ---- 全局异常处理 (脱敏) ----
    register_exception_handlers(app)

    # ---- 业务路由 ----
    app.include_router(auth.router)
    app.include_router(stocks.router)
    app.include_router(kline.router)
    app.include_router(tasks.router)
    app.include_router(backtest.router)
    app.include_router(system.router)
    app.include_router(scheduler.router)
    app.include_router(sources.router)
    app.include_router(kronos.router)
    app.include_router(train_auth.router)
    app.include_router(train_admin.router)
    app.include_router(train.router)
    app.include_router(train_stats.router)
    app.include_router(train_indices.router)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}

    # ---- 前端托管 ----
    frontend_dir = settings.FRONTEND_DIR
    if frontend_dir.exists() and (frontend_dir / "index.html").exists():
        assets_dir = frontend_dir / "assets"
        if assets_dir.exists():
            app.mount(
                "/assets",
                StaticFiles(directory=str(assets_dir)),
                name="assets",
            )

        index_html = frontend_dir / "index.html"

        @app.get("/")
        def index():
            return FileResponse(str(index_html))

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str, request: Request):
            """SPA 兜底:所有非 /api / /assets 的路径都返回 index.html"""
            if full_path.startswith(("api", "docs", "redoc", "openapi")):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            target = frontend_dir / full_path
            if target.is_file():
                return FileResponse(str(target))
            return FileResponse(str(index_html))
    else:
        @app.get("/")
        def no_frontend():
            return {
                "message": "前端未构建。请在 frontend/ 目录运行 npm install && npm run build",
                "frontend_dir": str(frontend_dir),
                "api_docs": "/docs",
            }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level="info",
    )