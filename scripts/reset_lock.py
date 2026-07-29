"""手动重置 ctt 用户失败计数(供调试 / 测试前清理)。"""
import sqlite3

DB_PATH = r"d:\AI\tradedojo\backend\data\stock.db"
USERNAME = "ctt"

c = sqlite3.connect(DB_PATH)
cur = c.execute(
    "UPDATE admin_user SET failed_attempts=0, last_failed_login=NULL WHERE username=?",
    (USERNAME,),
)
c.commit()
print(f"reset: {cur.rowcount} row(s) for username={USERNAME}")
c.close()
