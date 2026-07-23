"""
SQLite 数据库操作封装
- 自动初始化 schema
- 提供连接上下文管理器
- WAL 模式提升读写并发
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Sequence, Any

from config import DB_PATH, PROJECT_ROOT


@contextmanager
def get_conn():
    """获取 SQLite 连接(上下文管理器)"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(verbose: bool = True) -> None:
    """从 schema.sql 初始化所有表结构, 并对老库做必需的 ALTER 兼容"""
    schema_file = PROJECT_ROOT / "db" / "schema.sql"
    with open(schema_file, "r", encoding="utf-8") as f:
        sql_script = f.read()
    with get_conn() as conn:
        conn.executescript(sql_script)

        # ---- 在线 ALTER: 老库补字段(代码运行幂等,已存在的列不报错) ----
        def ensure_col(table: str, col_def: str, col_name: str):
            try:
                conn.execute(f"SELECT {col_name} FROM {table} LIMIT 1")
            except Exception:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")

        ensure_col("redeem_code", "revoked INTEGER DEFAULT 0", "revoked")
        # 给加完的列补索引
        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_redeem_revoked ON redeem_code(revoked)")
        except Exception:
            pass

        # 补 admin_action_log 表(IF NOT EXISTS 已处理)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS admin_action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL,
                actor_kind TEXT DEFAULT 'admin',
                action TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                detail_json TEXT,
                reason TEXT,
                before_value TEXT,
                after_value TEXT,
                ip TEXT,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_action_log_actor ON admin_action_log(actor, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_action_log_target ON admin_action_log(target_type, target_id);
        """)

    if verbose:
        print(f"[DB] 数据库已初始化: {DB_PATH}")


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    """执行单条 SQL,返回受影响行数"""
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.rowcount


def executemany(sql: str, seq: Iterable[Sequence[Any]]) -> int:
    """批量执行"""
    with get_conn() as conn:
        cur = conn.executemany(sql, seq)
        return cur.rowcount


def query_one(sql: str, params: Sequence[Any] = ()):
    """查询单行"""
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchone()


def query_all(sql: str, params: Sequence[Any] = ()):
    """查询多行"""
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall()


def table_count(table_name: str) -> int:
    """获取表行数"""
    row = query_one(f"SELECT COUNT(*) FROM {table_name}")
    return row[0] if row else 0


if __name__ == "__main__":
    init_db()
    print("Tables:")
    for row in query_all("SELECT name FROM sqlite_master WHERE type='table'"):
        print(f"  - {row[0]}")
