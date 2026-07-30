"""快速检查 user.db 是否建好"""
import sqlite3
c = sqlite3.connect("data/user.db")
print("user.db tables:", sorted([r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]))
c2 = sqlite3.connect("data/stock.db")
print("stock.db tables:", sorted([r[0] for r in c2.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]))
