#!/usr/bin/env bash
# 一键启动后端 —— 依赖由 uv 管理
set -e

cd "$(dirname "$0")"
echo "[1/2] 同步依赖 (uv sync) ..."
uv sync

echo "[2/2] 启动服务 (uv run main.py) ..."
exec uv run main.py