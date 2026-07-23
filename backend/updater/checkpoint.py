"""
断点续传管理器

三层快照保护:
1. 内存 dict  - 进程内最快访问
2. SQLite 表  - 持久化、可查询
3. JSON 文件  - 兜底,DB 损坏时仍可恢复
"""
import json
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from typing import Dict, Optional

from config import CHECKPOINT_DIR
from db.database import get_conn

logger = logging.getLogger(__name__)


class CheckpointManager:
    """管理单任务的断点续传状态"""

    def __init__(self, task_name: str, max_retry: int = 3):
        self.task_name = task_name
        self.max_retry = max_retry
        self.table_name = f"checkpoint_{task_name}"
        self.snapshot_file = CHECKPOINT_DIR / f"{task_name}.json"
        self.snapshot_tmp = CHECKPOINT_DIR / f"{task_name}.json.tmp"

        # 内存状态
        self.completed: set = set()
        self.failed: Dict[str, dict] = {}

        self._ensure_table()
        self._load()

    def _ensure_table(self):
        with get_conn() as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    code         TEXT PRIMARY KEY,
                    status       TEXT,
                    row_count    INTEGER DEFAULT 0,
                    retry_count  INTEGER DEFAULT 0,
                    last_error   TEXT,
                    updated_at   TEXT
                )
            """)

    def _load(self):
        """优先从 JSON 文件加载,文件不存在则从 DB 加载"""
        # 1. 文件快照
        if self.snapshot_file.exists():
            try:
                data = json.loads(self.snapshot_file.read_text(encoding="utf-8"))
                self.completed = set(data.get("completed", []))
                self.failed = data.get("failed", {})
                logger.info(
                    f"[CP] 从文件恢复: {len(self.completed)} 完成, "
                    f"{len(self.failed)} 待重试"
                )
                return
            except Exception as e:
                logger.warning(f"[CP] 快照文件损坏,回退到 DB: {e}")

        # 2. DB 恢复
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    f"SELECT code, status, retry_count, last_error "
                    f"FROM {self.table_name}"
                ).fetchall()
            for code, status, retry, err in rows:
                if status == "success":
                    self.completed.add(code)
                elif retry < self.max_retry:
                    self.failed[code] = {
                        "error": err or "", "retry": retry
                    }
            logger.info(
                f"[CP] 从 DB 恢复: {len(self.completed)} 完成, "
                f"{len(self.failed)} 待重试"
            )
        except Exception as e:
            logger.warning(f"[CP] DB 恢复失败: {e}")

    def mark_success(self, code: str, row_count: int = 0):
        self.completed.add(code)
        self.failed.pop(code, None)
        with get_conn() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO {self.table_name} "
                f"(code, status, row_count, retry_count, last_error, updated_at) "
                f"VALUES (?, 'success', ?, 0, NULL, ?)",
                (code, row_count, datetime.now().isoformat())
            )
        self._maybe_save()

    def mark_failed(self, code: str, error: str):
        retry = self.failed.get(code, {"retry": 0})["retry"] + 1
        self.failed[code] = {"error": error[:200], "retry": retry}
        with get_conn() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO {self.table_name} "
                f"(code, status, row_count, retry_count, last_error, updated_at) "
                f"VALUES (?, 'failed', 0, ?, ?, ?)",
                (code, retry, error[:200], datetime.now().isoformat())
            )
        self._maybe_save()

    def is_done(self, code: str) -> bool:
        return code in self.completed

    def need_retry(self, code: str) -> bool:
        if code in self.completed:
            return False
        if code not in self.failed:
            return True
        return self.failed[code]["retry"] < self.max_retry

    def _maybe_save(self):
        """每 50 次变更保存一次 JSON 快照"""
        if (len(self.completed) + len(self.failed)) % 50 == 0:
            self.save_snapshot()

    def save_snapshot(self):
        """原子写入 JSON 快照"""
        data = {
            "completed": list(self.completed),
            "failed": self.failed,
            "saved_at": datetime.now().isoformat()
        }
        try:
            self.snapshot_tmp.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
            self.snapshot_tmp.replace(self.snapshot_file)
        except Exception as e:
            logger.warning(f"[CP] 快照保存失败: {e}")

    def reset(self):
        """重置断点(慎用!)"""
        self.completed.clear()
        self.failed.clear()
        with get_conn() as conn:
            conn.execute(f"DELETE FROM {self.table_name}")
        if self.snapshot_file.exists():
            self.snapshot_file.unlink()

    def summary(self) -> dict:
        return {
            "task": self.task_name,
            "completed": len(self.completed),
            "pending_retry": len(self.failed),
            "max_retry": self.max_retry,
        }


# 简易测试
if __name__ == "__main__":
    from db.database import init_db
    init_db(verbose=False)

    cp = CheckpointManager("test_task")
    print("初始状态:", cp.summary())

    cp.mark_success("600000")
    cp.mark_failed("000001", "网络超时")
    cp.mark_success("000002", 100)
    print("操作后:", cp.summary())
    print("000001 need_retry:", cp.need_retry("000001"))
    print("000002 is_done:", cp.is_done("000002"))

    cp.save_snapshot()
    print("快照已保存")

    # 模拟重启
    cp2 = CheckpointManager("test_task")
    print("重启后:", cp2.summary())
