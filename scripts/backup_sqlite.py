"""
SQLite 安全备份脚本(跨平台,生产建议接入 cron / Windows 任务计划)
- 使用 sqlite3.Connection.backup() 拿到一致性快照(避免文件被占用)
- 默认保留 7 天
- 输出文件名带时间戳

用法:
    python scripts/backup_sqlite.py [--src PATH] [--dst DIR] [--keep-days 7]
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "backend" / "data" / "stock.db"
DEFAULT_DST = ROOT / "backups"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=str(DEFAULT_SRC))
    parser.add_argument("--dst", default=str(DEFAULT_DST))
    parser.add_argument("--keep-days", type=int, default=7)
    args = parser.parse_args()

    src = Path(args.src)
    dst = Path(args.dst)
    if not src.exists():
        print(f"[ERR] 源数据库不存在: {src}")
        return 1
    dst.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = dst / f"stock_{ts}.db"
    # 同时备份 WAL/SHM(若有)
    wal = Path(str(src) + "-wal")
    shm = Path(str(src) + "-shm")

    import sqlite3
    try:
        with sqlite3.connect(str(src)) as src_conn:
            with sqlite3.connect(str(target)) as dst_conn:
                src_conn.backup(dst_conn)
    except Exception as e:
        print(f"[ERR] 备份失败: {e}")
        return 2

    # 复制 wal/shm
    for aux in (wal, shm):
        if aux.exists():
            shutil.copy2(aux, dst / aux.name)

    print(f"[OK ] 备份完成: {target}")

    # 清理过期
    cutoff = datetime.now() - timedelta(days=args.keep_days)
    removed = 0
    for f in dst.iterdir():
        if not f.is_file():
            continue
        if not f.name.startswith("stock_"):
            continue
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            continue
    if removed:
        print(f"[CLEAN] 已清理 {removed} 个过期备份")
    return 0


if __name__ == "__main__":
    sys.exit(main())