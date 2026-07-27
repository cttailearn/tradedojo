"""
一键端到端测试脚本:
- 注册训练用户
- 管理员登录 → 生成兑换码
- 训练用户兑换码 → 充值
- 发起训练会话
- 时间推进多次
- 买入
- 卖出
- 看资金曲线/权益
- 结束
对每个步骤打印关键指标和返回摘要.
"""
import json, sys, time
import urllib.request, urllib.error
import urllib.parse as up
import random, string
import sqlite3
import io
from pathlib import Path

# 让 Windows console 不被 gb2312 截断中文 + emoji
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = "http://127.0.0.1:8765"
DB = Path(r"d:\AI\tradedojo\backend\data\stock.db")


def req(method, path, *, headers=None, body=None, raw=False):
    url = f"{BASE}{path}"
    data = None
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers: h.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        resp = urllib.request.urlopen(r, timeout=60)
        code = resp.status
        body_b = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(body_b) if body_b else None
        return code, payload
    except urllib.error.HTTPError as e:
        try: payload = json.loads(e.read().decode("utf-8"))
        except Exception: payload = None
        return e.code, payload
    except Exception as e:
        return 0, {"err": str(e)}


def step(title, code, payload, expect_ok=True):
    head = "[OK]" if (200 <= code < 300 or (not expect_ok)) else "[FAIL]"
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"\n{head} {title} -> HTTP {code}")
    if payload is not None:
        snippet = json.dumps(payload, ensure_ascii=False)[:500]
        print(f"    body: {snippet}{'…' if len(snippet) >= 500 else ''}")
    if code < 200 or code >= 300 and expect_ok:
        return False
    return True


def main():
    print("=" * 70)
    print("TradeDojo 训练端 E2E 测试 (uv + SQLite, 端口 8765)")
    print("=" * 70)

    # ---- 0. health
    c, p = req("GET", "/api/health")
    step("0. health", c, p)

    # ---- 1. register a brand new user
    uname = "tester_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    pwd = "Test1234xX"
    print(f"  ↪ use username={uname}")
    c, p = req("POST", "/api/train/register", body={"username": uname, "password": pwd, "nickname": "测试员"})
    if not step("1. 注册训练用户", c, p):
        # 可能已被占用 → 改为登录
        c2, p2 = req("POST", "/api/train/login", body={"username": uname, "password": pwd})
        if not step("1b 改用登录", c2, p2):
            return
        p = p2
    token = p.get("access_token") or p.get("token")
    print(f"  ↪ token (first 40 chars): {token[:40]}…")
    train_hdr = {"Authorization": f"Bearer {token}"}

    # ---- 2. login as admin
    c, p = req("POST", "/api/auth/login", body={"username": "ctt", "password": "ctt584520"})
    step("2. 管理员登录", c, p)
    admin_token = p.get("access_token") if (p and "access_token" in p) else None
    admin_hdr = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

    # ---- 3. create a redeem code (admin)
    if admin_token:
        c, p = req("POST", "/api/train/admin/redeem-codes",
                   headers=admin_hdr, body={"amount": 5000, "count": 1, "note": "e2e auto"})
        step("3. 管理员生成兑换码", c, p)
        codes = (p or {}).get("items") or (p or {}).get("codes") or []
        if isinstance(p, dict) and "code" in p: codes = [p["code"]]
        # 数据库直接读最新未使用码最稳
        with sqlite3.connect(str(DB)) as con:
            row = con.execute("SELECT code, amount FROM redeem_code WHERE revoked=0 AND is_used=0 "
                              "AND amount=5000 ORDER BY created_at DESC LIMIT 1").fetchone()
        if row:
            code_str = row[0]; amount = row[1]
            print(f"  ↪ 最新可用兑换码: {code_str} (面值 {amount})")
        else:
            print("  ⚠️ 没拿到兑换码,跳过充值步骤,balance 不足将不能开始训练")
            code_str = None; amount = None
    else:
        code_str = None

    # ---- 4. redeem
    if code_str:
        c, p = req("POST", "/api/train/redeem", headers=train_hdr, body={"code": code_str})
        step("4. 训练端兑换码充值", c, p)

    # ---- 4b. check wallet
    c, p = req("GET", "/api/train/wallet", headers=train_hdr)
    step("4b. 当前钱包", c, p)
    wallet_bal = ((p or {}).get("balance") if p else 0)

    if not wallet_bal or wallet_bal < 100:
        print("\n⚠️ 钱包余额不足,直接往 DB 里注入一个钱包记录(测试用)")
        try:
            with sqlite3.connect(str(DB)) as con:
                uid_row = con.execute("SELECT id FROM training_user WHERE username=?", (uname,)).fetchone()
                if uid_row:
                    uid = uid_row[0]
                    con.execute("INSERT INTO training_wallet(user_id, balance, total_topup) VALUES(?, 1000, 1000) "
                                "ON CONFLICT(user_id) DO UPDATE SET balance = balance + 1000, total_topup = total_topup + 1000",
                                (uid,))
                    print(f"  已为 uid={uid} 注入 1000 元训练资金")
        except Exception as e:
            print(f"  注入失败: {e}")

    # ---- 5. start a training session
    # 取一个比较保险的 start/end(数据是 2021-2026)
    payload = {
        "start_date": "2024-01-02",
        "end_date":   "2024-12-30",
        "lookback_months": 3,
        "initial_cash": 1_000_000,
        "commission_rate": 0.0003,
        "min_commission": 5,
        "stamp_tax": 0.001,
        "transfer_fee": 0.00001,
        "allow_split": True,
        "max_positions": 3,
        "per_trade_amount": 50_000,
        "allow_chinext": False,
        "allow_st": False,
        "allow_kcb": False,
        "allow_bj": False,
    }
    c, p = req("POST", "/api/train/sessions/start", headers=train_hdr, body=payload)
    step("5. 发起训练(随机选股 + 扣费)", c, p)
    if not p or "id" not in p:
        print("\n❌ 未拿到 session_id,中止")
        return
    session = p
    sid = session["id"]
    code = session["code"]; name = session.get("name")
    print(f"  ↪ session_id={sid}, 股票={name} ({code}), 训练区间 {session.get('start_date')} ~ {session.get('end_date')}, 钱包余额={session.get('wallet_balance_after')}")

    # ---- 6. advance +5 days
    c, p = req("POST", f"/api/train/sessions/{sid}/advance",
               headers=train_hdr, body={"days": 5})
    step("6. 推进 5 天", c, p)
    print(f"  ↪ current_date={p.get('current_date') if p else '-'}, total_equity={p.get('total_equity') if p else '-'}")

    # ---- 7. buy
    buy = {"side": "BUY", "amount": 50_000}
    c, p = req("POST", f"/api/train/sessions/{sid}/trade", headers=train_hdr, body=buy)
    step("7. 买入 5万元", c, p)
    if p: print(f"  ↪ 买入后持仓: {p.get('positions')},现金={p.get('cash')},权益={p.get('total_equity')}")

    # ---- 7b. check per-trade limit
    c, p = req("POST", f"/api/train/sessions/{sid}/trade", headers=train_hdr, body={"side": "BUY", "amount": 999999_99})
    step("7b. 超大金额买入(应被拒)", c, p, expect_ok=False)

    # ---- 8. advance +5 again to give price some movement
    c, p = req("POST", f"/api/train/sessions/{sid}/advance", headers=train_hdr, body={"days": 5})
    step("8. 再推进 5 天", c, p)
    print(f"  ↪ current_date={p.get('current_date') if p else '-'}, current_price={((p or {}).get('current_bar') or {}).get('close')}")

    # ---- 9. sell half (use first position qty)
    pos = (p or {}).get("positions") or []
    me = next((x for x in pos if x["code"] == code), None)
    if me and me.get("quantity"):
        half = int(me["quantity"]) // 2 // 100 * 100
        if half > 0:
            c, p = req("POST", f"/api/train/sessions/{sid}/trade",
                       headers=train_hdr, body={"side": "SELL", "quantity": half})
            step(f"9. 卖出一半 ({half} 股)", c, p)
        else:
            print("  ↪ position 过小,跳过卖出")
    else:
        print("  ↪ 没有持仓,跳过卖出")

    # ---- 10. equity curve
    c, p = req("GET", f"/api/train/sessions/{sid}/equity", headers=train_hdr)
    step("10. 资金曲线", c, p)
    eq = (p or {}).get("items") or []
    print(f"  ↪ 资金曲线点数: {len(eq)},首点={eq[0] if eq else '-'},末点={eq[-1] if eq else '-'}")

    # ---- 11. kline (daily/weekly/monthly)
    for p_ in ("daily", "weekly", "monthly"):
        c, p = req("GET", f"/api/train/sessions/{sid}/kline?period={p_}", headers=train_hdr)
        items = (p or {}).get("items") or []
        step(f"11/{p_}. K线({p_}) 共 {len(items)} 根", c, {"period": p_, "count": len(items), "first": items[0] if items else None, "last": items[-1] if items else None})

    # ---- 12. train indices endpoint (训练端独立路由)
    c, p = req("GET", "/api/train/indices", headers=train_hdr)
    step("12. 训练端指数清单", c, {"count": len((p or {}).get("items") or []),
                                    "first": (p or {}).get("items", [None])[0]})
    c, p = req("GET", "/api/train/indices/kline?code=sh000001&start=2024-01-02&end=2024-01-16&limit=20",
               headers=train_hdr)
    items = (p or {}).get("items") or []
    step("12b. 训练端拉上证综指 K线", c, {"count": len(items), "first": items[0] if items else None})

    # ---- 13. finish
    c, p = req("POST", f"/api/train/sessions/{sid}/finish", headers=train_hdr)
    step("13. 结束训练", c, p)
    print(f"  ↪ 最终 status={p.get('status') if p else '-'}, total_pnl={p.get('total_pnl') if p else '-'}")

    # ---- 14. sessions list
    c, p = req("GET", "/api/train/sessions", headers=train_hdr)
    items = (p or {}).get("items") or []
    step(f"14. 我的训练会话列表 (共 {len(items)} 条)", c, {"ids": [x.get("id") for x in items]})


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback; traceback.print_exc()
