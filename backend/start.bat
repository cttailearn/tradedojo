@echo off
REM Windows 一键启动 —— 依赖由 uv 管理
cd /d "%~dp0"

echo [1/2] 同步依赖 (uv sync) ...
uv sync || (echo 需要先安装 uv: https://docs.astral.sh/uv/ ^& pause & exit /b 1)

echo [2/2] 启动服务 (uv run main.py) ...
uv run main.py
pause