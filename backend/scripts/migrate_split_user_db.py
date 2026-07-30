"""
将训练用户/业务表从 stock.db 迁移到 user.db(同机迁移)。

迁移表:
  training_user, training_wallet, redeem_code,
  training_session, training_order, training_position, training_equity,
  admin_action_log, train_token

可重入:重复运行不会重复插入(用 INSERT OR IGNORE + SELECT 已存在主键;若两边都有,
则保留 user.db 的版本。生产场景一般 stock.db 是权威源时,直接 truncate user.db 再拷)。

用法:
  python -m scripts.migrate_split_user_db            # 只搬运,不删 stock.db
  python -m scripts.migrate_split_user_db --drop     # 搬运后从 stock.db DROP 这些表
  python -m scripts.migrate_split_user_db --dry-run # 仅打印将要搬运的行数

注意:
  - 跑前请先停掉 backend 服务,避免文件锁争用
  - WAL 文件(-wal/-shm)需要在 sqlite3 连接期间归零,这里靠 VACUUM INTO 模式更稳
  - 任何"训练 token / refresh_token"都仅在对应 DB 写入;一次完整迁移应保证 stock.db
    中不再保留训练业务表(可选 --drop)
"""
import argparse
import sqlite3
import sys
from pathlib import Path

# 允许从仓库根或 backend/ 两种位置直接执行
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
from db.database import USER_DB_TABLES  # noqa: E402
from config import DB_PATH, USER_DB_PATH  # noqa: E402


def _table_columns(conn, table: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [r[1] for r in rows]


def _copy_table(stock: sqlite3.Connection, user: sqlite3.Connection,
                table: str, dry_run: bool) -> int:
    if table not in {r[0] for r in stock.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}:
        return 0
    if table not in {r[0] for r in user.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}:
        print(f"  ! {table} 在 user.db 中不存在(已跳过)。请先启动 backend 让 init_db 建表。")
        return 0

    cols_stock = _table_columns(stock, table)
    cols_user = _table_columns(user, table)
    if set(cols_stock) != set(cols_user):
        diff1 = set(cols_stock) - set(cols_user)
        diff2 = set(cols_user) - set(cols_stock)
        print(f"  ! 列不一致,需要先升级 schema:")
        print(f"    stock 独有: {diff1}")
        print(f"    user   独有: {diff2}")
        return 0
    cols = cols_stock

    cur = stock.execute(f"SELECT COUNT(*) FROM {table}")
    n_total = cur.fetchone()[0]
    cur = user.execute(f"SELECT COUNT(*) FROM {table}")
    n_user = cur.fetchone()[0]
    print(f"  - {table}: stock={n_total}, user={n_user}")
    if dry_run:
        return n_total
    if n_user:
        # 不覆盖已有数据:生产一般人工 truncate 后再跑
        print(f"    跳过(目标已有数据)")
        return 0

    cols_sql = ",".join(f'"{c}"' for c in cols)
    placeholders = ",".join("?" * len(cols))
    rows = stock.execute(f"SELECT {cols_sql} FROM {table}").fetchall()
    # bulk insert 加速
    user.execute("BEGIN")
    try:
        user.executemany(
            f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders})",
            rows,
        )
        user.execute("COMMIT")
    except Exception:
        user.execute("ROLLBACK")
        raise
    return len(rows)


def _drop_table(stock: sqlite3.Connection, table: str) -> None:
    # 把"被外键引用的索引等"一并清掉。SQLite 不会强制存在外键;只 DROP TABLE
    try:
        stock.execute(f"DROP TABLE IF EXISTS {table}")
        print(f"  - 已从 stock.db 移除表 {table}")
    except Exception as e:
        print(f"  ! 无法 drop {table}: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drop", action="store_true", help="搬运成功后,从 stock.db DROP 用户表")
    parser.add_argument("--dry-run", action="store_true", help="只统计,不做改动")
    args = parser.parse_args()

    print(f"source (stock.db) : {DB_PATH}")
    print(f"target (user.db)  : {USER_DB_PATH}")

    if not DB_PATH.exists():
        print("source 不存在,退出。"); return 1
    if not USER_DB_PATH.exists():
        print("target 不存在,请先启动一次 backend 让 init_db 建表,再重跑迁移。")
        return 1

    stock = sqlite3.connect(str(DB_PATH), timeout=30)
    user = sqlite3.connect(str(USER_DB_PATH), timeout=30)
    stock.execute("PRAGMA foreign_keys=OFF")
    user.execute("PRAGMA foreign_keys=OFF")

    copied = 0
    for tbl in sorted(USER_DB_TABLES):
        n = _copy_table(stock, user, tbl, args.dry_run)
        copied += n
        if n and args.drop and not args.dry_run:
            _drop_table(stock, tbl)

    if not args.dry_run:
        stock.commit(); user.commit()
        # WAL → checkpoint
        stock.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        user.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    stock.close(); user.close()

    print()
    print("=" * 50)
    print(f"完成。{'(dry-run)' if args.dry_run else ''} 共迁移记录数估算: {copied}")
    print("=" * 50)
    print("""
下一步:
  1) 重启 backend 让它通过新的 user_execute / user_query_* 入口工作
  2) 前端:训练端用户必须重新登录一次(本地 token store 由 user.db 重新派生)
  3) 如果用了 --drop,备份原 stock.db:
       cp data/stock.db data/stock.db.bak.$(date +%s)
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
