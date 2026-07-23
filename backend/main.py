"""
后端启动入口 —— `cd backend && uv run main.py` 即可启动

- 通过 pyproject.toml 由 uv 管理依赖
- 默认监听 0.0.0.0:8000,可通过环境变量覆盖:
    STOCK_HOST / STOCK_PORT
"""
import os
import sys
import uvicorn

# 把 backend/ 自身加入 sys.path,保证 app.* 能被绝对导入
_BACKEND = os.path.dirname(os.path.abspath(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.main import app  # noqa: E402
from app.config import settings  # noqa: E402


def run():
    """uvicorn 启动"""
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        reload=bool(int(os.environ.get("STOCK_RELOAD", "0"))),
        log_level="info",
    )


if __name__ == "__main__":
    run()