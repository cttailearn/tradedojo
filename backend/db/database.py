"""
SQLite 数据库操作封装
- 自动初始化 schema (拆分为 stock.db + user.db)
- 提供连接上下文管理器:get_conn()(stock) / get_user_conn()(训练业务)
- WAL 模式提升读写并发
"""
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Sequence, Any

from config import DB_PATH, USER_DB_PATH, PROJECT_ROOT


# ------------ 表归属 ------------
# user.db 包含的训练用户/训练业务/审计表。
USER_DB_TABLES: set[str] = {
    "training_user",
    "training_wallet",
    "redeem_code",
    "training_session",
    "training_order",
    "training_position",
    "training_equity",
    "admin_action_log",
    "train_token",
}


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_conn():
    """stock.db 连接 (股票数据 + admin_user + 管理端 refresh_token)"""
    conn = _connect(DB_PATH)
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_user_conn():
    """user.db 连接 (训练用户/钱包/兑换码/会话/订单/管理员审计/训练 token)"""
    conn = _connect(USER_DB_PATH)
    try:
        yield conn
    except Exception:
        conn.rollback()
    finally:
        conn.close()


# =====================================================================
# 训练业务专用入口(user.db)。
# 默认 get_conn/execute/query_* 仍走 stock.db(向后兼容)。
# =====================================================================
def user_execute(sql: str, params: Sequence[Any] = ()) -> int:
    with get_user_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.rowcount


def user_executemany(sql: str, seq: Iterable[Sequence[Any]]) -> int:
    with get_user_conn() as conn:
        cur = conn.executemany(sql, seq)
        return cur.rowcount


def user_query_one(sql: str, params: Sequence[Any] = ()):
    with get_user_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchone()


def user_query_all(sql: str, params: Sequence[Any] = ()):
    with get_user_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall()


def _split_schema_by_db(schema_sql: str) -> tuple[str, str]:
    """把 schema.sql 按 USER_DB_TABLES 拆成两段。

    策略:逐条解析 CREATE TABLE / CREATE INDEX 块,落入对应库。
    """
    statements: list[str] = []
    buf: list[str] = []
    depth = 0
    for line in schema_sql.splitlines(keepends=False):
        buf.append(line)
        opens = line.count("(")
        closes = line.count(")")
        depth += opens - closes
        if depth <= 0 and line.strip().endswith(";"):
            statements.append("\n".join(buf).strip())
            buf = []
    stock_sql: list[str] = []
    user_sql: list[str] = []

    def _target_table(stmt: str) -> str | None:
        m = re.search(
            r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?[\w\"]+\s+ON\s+([\w\"]+)",
            stmt, re.I,
        )
        if m:
            return m.group(1).strip('"')
        m = re.search(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w\"]+)",
            stmt, re.I,
        )
        if m:
            return m.group(1).strip('"')
        return None

    for stmt in statements:
        if not stmt:
            continue
        tgt = _target_table(stmt)
        target = user_sql if (tgt and tgt in USER_DB_TABLES) else stock_sql
        target.append(stmt)

    return "\n\n".join(stock_sql), "\n\n".join(user_sql)


def init_db(verbose: bool = True) -> None:
    """从 schema.sql 初始化:
       - stock 表 → stock.db
       - USER_DB_TABLES 表 → user.db

       老库(stock.db)仍做兼容性 ALTER 补丁;对 user.db 做同样幂等补丁。
    """
    schema_file = PROJECT_ROOT / "db" / "schema.sql"
    with open(schema_file, "r", encoding="utf-8") as f:
        sql_script = f.read()
    stock_sql, user_sql = _split_schema_by_db(sql_script)

    # ---- stock.db ----
    with get_conn() as conn:
        if stock_sql:
            conn.executescript(stock_sql)

        def ensure_col(table: str, col_def: str, col_name: str):
            try:
                conn.execute(f"SELECT {col_name} FROM {table} LIMIT 1")
            except Exception:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")

        # stock_list 增强列(由 stock_enrich updater 写入,旧库通过 ensure_col 幂等追加)
        ensure_col("stock_list", "total_share     REAL",         "total_share")
        ensure_col("stock_list", "float_share     REAL",         "float_share")
        ensure_col("stock_list", "industry_detail TEXT",         "industry_detail")
        ensure_col("stock_list", "last_enriched_at TEXT",        "last_enriched_at")

        # 定时调度 job 配置表(每类数据一个 job,可独立启停/改 cron/改参数)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS scheduler_job (
                task         TEXT PRIMARY KEY,
                cron         TEXT NOT NULL,
                enabled      INTEGER NOT NULL DEFAULT 1,
                params_json  TEXT NOT NULL DEFAULT '{}',
                updated_at   TEXT DEFAULT (datetime('now', 'localtime')),
                last_run_at  TEXT,
                last_status  TEXT
            );
        """)

        try:
            from updater.types import DEFAULT_JOBS
            import json as _json
            existing = {r[0] for r in conn.execute("SELECT task FROM scheduler_job").fetchall()}
            for task, cron, enabled, params in DEFAULT_JOBS:
                if task not in existing:
                    conn.execute(
                        "INSERT INTO scheduler_job(task, cron, enabled, params_json) VALUES (?,?,?,?)",
                        (task, cron, 1 if enabled else 0, _json.dumps(params, ensure_ascii=False)),
                    )
        except Exception as e:
            print(f"[init_db] seed scheduler_job failed: {e}")

    # ---- user.db ----
    with get_user_conn() as conn:
        if user_sql:
            conn.executescript(user_sql)

        def ensure_col_u(table: str, col_def: str, col_name: str):
            try:
                conn.execute(f"SELECT {col_name} FROM {table} LIMIT 1")
            except Exception:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")

        ensure_col_u("redeem_code", "revoked INTEGER DEFAULT 0", "revoked")
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_redeem_revoked ON redeem_code(revoked)"
            )
        except Exception:
            pass

    if verbose:
        print(f"[DB] stock 数据库已初始化: {DB_PATH}")
        print(f"[DB] user  数据库已初始化: {USER_DB_PATH}")


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    """执行单条 SQL(stock.db),返回受影响行数"""
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.rowcount


def executemany(sql: str, seq: Iterable[Sequence[Any]]) -> int:
    """批量执行(stock.db)"""
    with get_conn() as conn:
        cur = conn.executemany(sql, seq)
        return cur.rowcount


def query_one(sql: str, params: Sequence[Any] = ()):
    """查询单行(stock.db)"""
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchone()


def query_all(sql: str, params: Sequence[Any] = ()):
    """查询多行(stock.db)"""
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall()


def table_count(table_name: str) -> int:
    """获取表行数 (stock.db)"""
    row = query_one(f"SELECT COUNT(*) FROM {table_name}")
    return row[0] if row else 0


if __name__ == "__main__":
    init_db()
    print("--- stock.db tables ---")
    for row in query_all("SELECT name FROM sqlite_master WHERE type='table'"):
        print(f"  - {row[0]}")
    print("--- user.db tables ---")
    with get_user_conn() as conn:
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            print(f"  - {row[0]}")
