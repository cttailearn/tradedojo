"""
数据库操作封装 —— 双驱动兼容层(SQLite 默认 + 可选 PostgreSQL)

- 默认 SQLite:拆分为 stock.db + user.db,行为与历史版本完全一致。
- 可选 PostgreSQL:STOCK_DB_DRIVER=postgres(见 config.DBConfig),get_conn /
  get_user_conn 连接同一个 PG 库(两库表名不冲突)。
- 对外 API 保持不变:
    execute / executemany / query_one / query_all / table_count
    user_execute / user_executemany / user_query_one / user_query_all
    get_conn / get_user_conn / init_db
  另新增导出:is_postgres(bool)、table_names(pattern=None)。

兼容层要点:
- Row:统一行对象,支持 row[0] / row['col'] / 按值迭代(元组语义)/
  len() / keys();fetchone 无数据返回 None。dict(zip(COLS, row))、
  dict(row)、元组解包等既有访问方式全部不变。
- Connection / Cursor 封装:execute/executemany/executescript/close/
  commit/rollback/total_changes;row_factory 赋值 = no-op。
  PG 分支执行前做 ? -> %s 翻译(已验证业务 SQL 字符串字面量中不含 '?'),
  并跳过 PRAGMA 语句。
- datetime() 兼容函数:PG 模式下注册同名函数,让业务里 21 处
  datetime('now','localtime') 与 datetime('now','-30 days') 零改动运行。
"""
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Sequence

from starlette.exceptions import HTTPException

from config import DB_PATH, USER_DB_PATH, PROJECT_ROOT, db_config


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


# ------------ 驱动选择 ------------
is_postgres: bool = db_config.is_postgres


# =====================================================================
# 统一 Row 对象
# =====================================================================
class Row:
    """统一行对象:支持 int 索引、列名字符串访问、按值迭代(元组语义)。

    - dict(zip(COLS, row)):依赖 __iter__ 按值迭代;
    - dict(row):CPython dict() 会优先走「有 keys() 的对象即视为 mapping」
      分支,配合 __getitem__(字符串) 即可工作;
    - fetchone() 无数据时返回 None(与 sqlite3 一致)。
    """

    __slots__ = ("_names", "_index", "_values")

    def __init__(self, names: tuple, index: dict, values: tuple):
        self._names = names
        self._index = index
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        if isinstance(key, str):
            return self._values[self._index[key]]
        raise TypeError(f"Row 索引必须是 int 或列名字符串,got {type(key).__name__}")

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        """返回列名元组(与 sqlite3.Row.keys() 一致)"""
        return self._names

    def __eq__(self, other):
        if isinstance(other, Row):
            return self._values == other._values
        if isinstance(other, tuple):
            return self._values == other
        return NotImplemented

    def __hash__(self):
        return hash(self._values)

    def __repr__(self):
        return f"Row({self._names}): {self._values!r}"


# =====================================================================
# PG 模式:SQL 翻译
# =====================================================================
_PG_PARAM_RE = re.compile(r"\?|%(?!s)")


def _translate_sql(sql: str, has_params: bool) -> str:
    """把 SQLite 占位符 ? 翻译为 psycopg3 的 %s。

    已核验:业务 SQL 字符串字面量中不含 '?'(占位符生成代码除外)。
    psycopg3 解析 %s 占位符时,查询文本里的字面量 '%' 必须写成 '%%',
    否则抛 unsupported placeholder 错误;仅当有参数时 psycopg3 才会做
    占位符解析,因此无参数时 '%' 保持原样(LIKE 'checkpoint_%' 等)。
    """
    if not has_params:
        return sql.replace("?", "%s")
    return _PG_PARAM_RE.sub(lambda m: "%s" if m.group(0) == "?" else "%%", sql)


_PG_PRAGMA_RE = re.compile(r"^\s*PRAGMA\b", re.IGNORECASE)


def _is_pragma(sql: str) -> bool:
    return bool(_PG_PRAGMA_RE.match(sql))


def _looks_like_insert(sql: str) -> bool:
    """粗略判断语句是否为 INSERT(用于 PG 模式 lastrowid)。"""
    s = sql.lstrip()
    # 跳过开头注释
    while s.startswith("--") or s.startswith("/*"):
        nl = s.find("\n")
        if nl == -1:
            return False
        s = s[nl + 1:].lstrip()
    return s[:6].upper() == "INSERT"


def _split_sql_statements(script: str) -> list[str]:
    """按分号切分 SQL 脚本,正确处理单引号字符串、-- 注释与 $$ 美元引用。

    PG 模式 executescript 使用:PG 不支持一次执行多条语句,
    需拆成单条逐条执行;datetime() 函数体里的分号在 $$...$$ 内,不会被误拆。
    """
    statements: list[str] = []
    buf: list[str] = []
    i, n = 0, len(script)
    in_single = False          # 单引号字符串内
    dollar_tag: str | None = None   # 美元引用标签(如 '$$' / '$tag$')
    while i < n:
        c = script[i]
        nxt = script[i + 1] if i + 1 < n else ""
        # -- 行注释(不在字符串/美元引用内才生效)
        if c == "-" and nxt == "-" and not in_single and dollar_tag is None:
            while i < n and script[i] != "\n":
                i += 1
            continue
        if in_single:
            buf.append(c)
            if c == "'":
                if nxt == "'":        # '' 转义单引号
                    buf.append(nxt)
                    i += 1
                else:
                    in_single = False
            i += 1
            continue
        if dollar_tag is not None:
            if script.startswith(dollar_tag, i):
                buf.append(dollar_tag)
                i += len(dollar_tag)
                dollar_tag = None
            else:
                buf.append(c)
                i += 1
            continue
        if c == "'":
            in_single = True
            buf.append(c)
            i += 1
            continue
        if c == "$":
            j = script.find("$", i + 1)
            if j != -1:
                tag = script[i:j + 1]
                dollar_tag = tag
                buf.append(tag)
                i = j + 1
                continue
        if c == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    stmt = "".join(buf).strip()
    if stmt:
        statements.append(stmt)
    return statements


# =====================================================================
# 统一游标 / 连接封装
# =====================================================================
class _NullCursor:
    """PG 模式下跳过 PRAGMA 语句时的空游标(无任何结果)。"""

    description = None
    rowcount = -1
    lastrowid = None

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        pass


class CompatCursor:
    """统一游标封装:fetchone/fetchall 把原生行包装为 Row。

    sqlite: 直接透传原生 sqlite3.Cursor 行为;
    pg:     基于 psycopg3 游标,rowcount/lastrowid 做兼容。
    """

    __slots__ = ("_cur", "_mode", "_conn", "_is_insert", "_spec_cache")

    def __init__(self, cur: Any, mode: str, conn: "CompatConnection"):
        self._cur = cur
        self._mode = mode
        self._conn = conn
        self._is_insert = False
        self._spec_cache: tuple | None = None

    # ---- 列名 / 行包装 ----
    def _col_names(self) -> tuple:
        desc = getattr(self._cur, "description", None)
        if not desc:
            return ()
        names = []
        for d in desc:
            if isinstance(d, str):
                names.append(d)
            elif hasattr(d, "name"):      # psycopg3 Column 对象
                names.append(d.name)
            else:                          # sqlite3 description 元组
                names.append(d[0])
        return tuple(names)

    def _spec(self) -> tuple:
        if self._spec_cache is None:
            names = self._col_names()
            self._spec_cache = (names, {n: i for i, n in enumerate(names)})
        return self._spec_cache

    def _row(self, raw):
        if raw is None:
            return None
        names, index = self._spec()
        return Row(names, index, raw)

    # ---- 读取 ----
    def fetchone(self):
        return self._row(self._cur.fetchone())

    def fetchall(self):
        return [self._row(r) for r in self._cur.fetchall()]

    @property
    def rowcount(self):
        return getattr(self._cur, "rowcount", -1)

    @property
    def description(self):
        return getattr(self._cur, "description", None)

    @property
    def lastrowid(self):
        """最后插入行的 id。

        sqlite: 原生 cursor.lastrowid;
        pg:     仅当上一条为 INSERT 时执行 SELECT lastval(),失败返回 None。
        """
        if self._mode == "sqlite":
            return getattr(self._cur, "lastrowid", None)
        if not self._is_insert:
            return None
        try:
            self._cur.execute("SELECT lastval()")
            raw = self._cur.fetchone()
            return raw[0] if raw else None
        except Exception:
            return None

    def close(self):
        try:
            self._cur.close()
        except Exception:
            pass

    # ---- 复用连接执行 ----
    def execute(self, sql: str, params=None):
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, seq):
        return self._conn.executemany(sql, seq)


class CompatConnection:
    """统一连接封装(兼容 sqlite3.Connection 与 psycopg3 Connection)。

    - execute / executemany / executescript / close / commit / rollback
    - total_changes 属性(sqlite 原生累加;pg 手工累加 rowcount)
    - row_factory 赋值 = no-op(行统一包装为 Row,不再区分 sqlite3.Row)
    - PG 分支自动做 ? -> %s 翻译并跳过 PRAGMA
    """

    def __init__(self, raw: Any, mode: str):
        self._conn = raw
        self._mode = mode
        self._pg_total_changes = 0

    # ---- 兼容属性 ----
    @property
    def row_factory(self):
        return None

    @row_factory.setter
    def row_factory(self, value):
        pass  # 行已统一为 Row;此处忽略赋值(如 sqlite3.Row)

    @property
    def total_changes(self) -> int:
        """连接以来累计变更行数。"""
        if self._mode == "sqlite":
            return self._conn.total_changes
        return self._pg_total_changes

    def _acc(self, n) -> None:
        if self._mode == "pg" and isinstance(n, int) and n > 0:
            self._pg_total_changes += n

    # ---- 执行 ----
    def execute(self, sql: str, params=None):
        if self._mode == "pg":
            if _is_pragma(sql):
                return CompatCursor(_NullCursor(), "pg", self)
            has_params = params is not None and len(params) > 0
            sql_t = _translate_sql(sql, has_params)
            cur = self._conn.cursor()
            try:
                if params is None:
                    cur.execute(sql_t)
                else:
                    cur.execute(sql_t, params)
            except Exception:
                cur.close()
                raise
            self._acc(cur.rowcount)
            cc = CompatCursor(cur, "pg", self)
            cc._is_insert = _looks_like_insert(sql)
            return cc
        # sqlite:保持原生行为不变
        cur = self._conn.execute(sql) if params is None else self._conn.execute(sql, params)
        return CompatCursor(cur, "sqlite", self)

    def executemany(self, sql: str, seq: Iterable[Sequence[Any]]):
        if self._mode == "pg":
            if _is_pragma(sql):
                return CompatCursor(_NullCursor(), "pg", self)
            sql_t = _translate_sql(sql, True)
            cur = self._conn.cursor()
            try:
                cur.executemany(sql_t, seq)
            except Exception:
                cur.close()
                raise
            self._acc(cur.rowcount)
            cc = CompatCursor(cur, "pg", self)
            cc._is_insert = _looks_like_insert(sql)
            return cc
        cur = self._conn.executemany(sql, seq)
        return CompatCursor(cur, "sqlite", self)

    def executescript(self, script: str):
        if self._mode == "pg":
            # PG 不支持一次执行多条语句:拆分后逐条执行,跳过 PRAGMA
            for stmt in _split_sql_statements(script):
                stmt = stmt.strip()
                if not stmt or _is_pragma(stmt):
                    continue
                self.execute(stmt)
            return
        self._conn.executescript(script)

    # ---- 生命周期 ----
    def close(self):
        self._conn.close()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def cursor(self):
        if self._mode == "pg":
            return CompatCursor(self._conn.cursor(), "pg", self)
        return CompatCursor(self._conn.cursor(), "sqlite", self)


# =====================================================================
# 连接创建
# =====================================================================
def _connect_sqlite(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _connect_pg():
    # 延迟导入:sqlite 模式无需 psycopg,即使未安装也不影响启动
    import psycopg

    return psycopg.connect(db_config.conninfo, autocommit=True)


def _open_conn(path: Path) -> CompatConnection:
    """按驱动打开连接;PG 模式下两个库共用同一个 PG 连接。"""
    if is_postgres:
        return CompatConnection(_connect_pg(), mode="pg")
    return CompatConnection(_connect_sqlite(path), mode="sqlite")


@contextmanager
def get_conn():
    """stock.db 连接 (股票数据 + admin_user + 管理端 refresh_token)。

    PG 模式下连接同一个 PostgreSQL 库(路径参数被忽略)。
    """
    conn = _open_conn(DB_PATH)
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_user_conn():
    """user.db 连接 (训练用户/钱包/兑换码/会话/订单/管理员审计/训练 token)。

    PG 模式下连接同一个 PostgreSQL 库(路径参数被忽略)。
    注意:保持历史行为——块内异常仅回滚,不向上抛出。
    """
    conn = _open_conn(USER_DB_PATH)
    try:
        yield conn
    except HTTPException:
        # 业务控制流异常必须向上传播(FastAPI 才能返回 4xx),
        # 否则会被误吞成 500(预存缺陷,2026-08-03 修复)
        conn.rollback()
        raise
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


def table_names(pattern: str | None = None) -> list[str]:
    """列出表名;可传 LIKE 模式过滤。供 sqlite_master 调用点迁移使用。

    - sqlite: 查询 sqlite_master
    - pg:     查询 pg_tables(schemaname='public')
    """
    if is_postgres:
        sql = "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        if pattern:
            sql += " AND tablename LIKE ?"
            rows = query_all(sql, (pattern,))
        else:
            rows = query_all(sql)
        return [r[0] for r in rows]
    sql = "SELECT name FROM sqlite_master WHERE type = 'table'"
    if pattern:
        sql += " AND name LIKE ?"
        rows = query_all(sql, (pattern,))
    else:
        rows = query_all(sql)
    return [r[0] for r in rows]


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


def _seed_scheduler_jobs(conn: CompatConnection) -> None:
    """幂等写入 DEFAULT_JOBS 到 scheduler_job(已存在则跳过)。"""
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


def init_db(verbose: bool = True) -> None:
    """初始化数据库。

    - sqlite: 与历史行为完全一致(拆 stock.db / user.db)。
    - pg:     执行 schema_pg.sql(首条即 datetime 兼容函数),再跑
      ensure_col 补列补丁 + scheduler_job 种子。
    """
    if is_postgres:
        _init_db_pg(verbose)
        return
    _init_db_sqlite(verbose)


def _init_db_sqlite(verbose: bool = True) -> None:
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

        # 2026-07-31 P1-7: key-value 配置表(主源选择等持久化设置)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                updated_at  TEXT DEFAULT (datetime('now', 'localtime'))
            );
        """)

        # 2026-07-31 P1-9: A 股交易日历(从指数 K线 推断)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS trading_calendar (
                trade_date  TEXT PRIMARY KEY,
                updated_at  TEXT DEFAULT (datetime('now', 'localtime'))
            );
            CREATE INDEX IF NOT EXISTS idx_trading_calendar_date
                ON trading_calendar(trade_date);
        """)

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

        _seed_scheduler_jobs(conn)

        # 2026-07-31 P0-5: 调度器启动检测错过的 cron (必须在 scheduler_job 建表后)
        ensure_col("scheduler_job", "last_missed_at TEXT",       "last_missed_at")
        ensure_col("scheduler_job", "missed_count   INTEGER DEFAULT 0", "missed_count")

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
        # 2026-07-31 优化: 限价单状态(P0-3)
        ensure_col_u("training_order", "pending_status TEXT DEFAULT 'filled'", "pending_status")
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_order_pending "
                "ON training_order(session_id, pending_status)"
            )
        except Exception:
            pass
        # 2026-07-31 P2-3: 训练风控规则
        ensure_col_u("training_session", "auto_stop_loss_pct REAL DEFAULT 0", "auto_stop_loss_pct")
        ensure_col_u("training_session", "auto_take_profit_pct REAL DEFAULT 0", "auto_take_profit_pct")

    if verbose:
        print(f"[DB] stock 数据库已初始化: {DB_PATH}")
        print(f"[DB] user  数据库已初始化: {USER_DB_PATH}")


def _init_db_pg(verbose: bool = True) -> None:
    """PostgreSQL 初始化:
       1. 执行 schema_pg.sql —— 首条语句即 datetime() 兼容函数(注册先于建表),
          随后创建全部表与索引(单库,含 admin_user/refresh_token 等内联 DDL)。
       2. ensure_col 兼容补列(探测 UndefinedColumn 后 ALTER TABLE ADD COLUMN)。
       3. 幂等写入 scheduler_job 种子(select-then-insert,PG 同样适用)。
    """
    import psycopg

    schema_file = PROJECT_ROOT / "db" / "schema_pg.sql"
    with open(schema_file, "r", encoding="utf-8") as f:
        sql_script = f.read()

    with get_conn() as conn:
        conn.executescript(sql_script)

        def ensure_col(table: str, col_def: str, col_name: str):
            try:
                conn.execute(f"SELECT {col_name} FROM {table} LIMIT 1")
            except psycopg.errors.UndefinedColumn:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")

        # stock_list 增强列(与 SQLite 分支同一批补丁)
        ensure_col("stock_list", "total_share     REAL",         "total_share")
        ensure_col("stock_list", "float_share     REAL",         "float_share")
        ensure_col("stock_list", "industry_detail TEXT",         "industry_detail")
        ensure_col("stock_list", "last_enriched_at TEXT",        "last_enriched_at")

        # scheduler_job 扩展列(2026-07-31 P0-5)
        ensure_col("scheduler_job", "last_missed_at TEXT",       "last_missed_at")
        ensure_col("scheduler_job", "missed_count   INTEGER DEFAULT 0", "missed_count")

        # 用户侧列补丁(与 SQLite 分支一致)
        ensure_col("redeem_code", "revoked INTEGER DEFAULT 0", "revoked")
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_redeem_revoked ON redeem_code(revoked)"
            )
        except Exception:
            pass
        ensure_col("training_order", "pending_status TEXT DEFAULT 'filled'", "pending_status")
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_order_pending "
                "ON training_order(session_id, pending_status)"
            )
        except Exception:
            pass
        ensure_col("training_session", "auto_stop_loss_pct REAL DEFAULT 0", "auto_stop_loss_pct")
        ensure_col("training_session", "auto_take_profit_pct REAL DEFAULT 0", "auto_take_profit_pct")

        _seed_scheduler_jobs(conn)

    if verbose:
        print(f"[DB] PostgreSQL 数据库已初始化: {db_config.conninfo}")


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
    print("--- stock 表 ---")
    for name in table_names():
        print(f"  - {name}")
    print("--- user 表 ---")
    with get_user_conn() as conn:
        if is_postgres:
            rows = conn.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            ).fetchall()
        else:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        for row in rows:
            print(f"  - {row[0]}")
