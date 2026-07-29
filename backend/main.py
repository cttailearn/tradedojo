"""
后端启动入口 —— `cd backend && uv run main.py` 即可启动

- 通过 pyproject.toml 由 uv 管理依赖
- 默认监听 0.0.0.0:8000,可通过环境变量覆盖:
    STOCK_HOST / STOCK_PORT

启动时会自动加载仓库根目录的 .env 文件(若存在);
已存在的进程环境变量优先级高于 .env,便于生产用 systemd EnvironmentFile 覆盖。
"""
import os
import sys
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

# 把 backend/ 自身加入 sys.path,保证 app.* 能被绝对导入
_BACKEND = os.path.dirname(os.path.abspath(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# 先注入 .env,再 import app.config(否则 settings 看不到 STOCK_SECRET_KEY 等)
_PROJECT_ROOT = Path(_BACKEND).parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)

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