"""
FastAPI 主入口
- 启动时初始化数据库(库表 + 默认管理员)
- 注册 CORS / 静态前端 / 路由
- 托管 Vite 构建产物 (frontend/dist/)
"""
import os

# HuggingFace 配置(用户可通过环境变量覆盖)
# 默认走 hf-mirror.com(国内友好);若有 VPN,可改为 https://huggingface.co
os.environ.setdefault("HF_ENDPOINT", os.environ.get("HF_ENDPOINT", "https://huggingface.co"))

import logging
import sys
from pathlib import Path

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
from db.database import init_db
from app.routers import auth, stocks, kline, tasks, backtest, system, scheduler, sources, kronos, train, train_auth, train_admin

logger = logging.getLogger("app")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="A 股数据库管理与回测系统",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 启动事件
    @app.on_event("startup")
    def _startup():
        logger.info("[STARTUP] 初始化数据库 ...")
        init_db(verbose=False)
        init_user_db()
        ensure_default_admin()
        logger.info(f"[STARTUP] 完成。前端目录: {settings.FRONTEND_DIR}")

    # 业务路由
    app.include_router(auth.router)
    app.include_router(stocks.router)
    app.include_router(kline.router)
    app.include_router(tasks.router)
    app.include_router(backtest.router)
    app.include_router(system.router)
    app.include_router(scheduler.router)
    app.include_router(sources.router)
    app.include_router(kronos.router)
    # 训练端(用户端 K 线交易训练)
    app.include_router(train_auth.router)
    app.include_router(train_admin.router)
    app.include_router(train.router)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}

    # ---- 前端托管 ----
    frontend_dir = settings.FRONTEND_DIR
    if frontend_dir.exists() and (frontend_dir / "index.html").exists():
        # Vite 产物在 dist/assets/,挂载为 /assets
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
            """
            SPA 兜底:所有非 /api / /assets 的路径都返回 index.html,
            前端 hash 路由会接管
            """
            # 避免和 OpenAPI/docs 冲突
            if full_path.startswith(("api", "docs", "redoc", "openapi")):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            # 真实存在的文件直接返回(如 favicon)
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