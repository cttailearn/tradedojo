"""
E2E 测试脚本 - K 线交易训练系统
覆盖:
  1) 注册 → 登录 → me/wallet
  2) 管理员生成兑换码
  3) 兑换码充值 + 一码一用 (二次使用应失败)
  4) 余额不足 → 无法发起训练
  5) 正常发起训练 → 随机选股 → 推进 + K线
  6) 买入 → 卖出 → 资金变化 + 已实现盈亏
  7) 强制边界:
      - 卖出超过持仓
      - 金额不足买 1 手
      - 推进到上限
      - 关闭的会话无法再推进/下单
"""
import json
import os
import sys
import time
import uuid
import urllib.request
import urllib.error

# 让 Windows gbk 控制台也能正常打印
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = "http://127.0.0.1:8001"


def http(method, path, token=None, body=None, expect=200):
    req = urllib.request.Request(
        BASE + path, method=method,
        headers={"Content-Type": "application/json"} |
                  ({"Authorization": f"Bearer {token}"} if token else {}),
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read())
            return resp.status, payload
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body.decode("utf-8", "ignore")}


def step(t):
    print(f"\n=== {t} ===")


def ok(cond, label):
    print(("[OK]" if cond else "[FAIL]"), label)
    return bool(cond)


def expect_status(actual, expected, label):
    print(("✅" if actual == expected else "❌"), f"[{actual}] {label} (expected {expected})")
    return actual == expected


def main():
    rand = uuid.uuid4().hex[:6]
    user = f"u_{rand}"
    pwd = "pwd123456"

    # ---------- 1) 注册 / 登录 ----------
    step("1) 注册 + 登录 + me/wallet")
    s, _ = http("POST", "/api/train/register", body={
        "username": user, "password": pwd, "display_name": "测试员"
    })
    ok(s == 200, f"register: {s}")
    s, data = http("POST", "/api/train/login", body={"username": user, "password": pwd})
    ok(s == 200 and data.get("access_token"), f"login: {s}")
    tkn = data["access_token"]
    s, data = http("GET", "/api/train/me", token=tkn)
    ok(s == 200, f"me: {s}, user={data.get('username')}")
    ok(data.get("wallet", {}).get("balance") == 0, "新用户余额 0")
    s, data = http("GET", "/api/train/wallet", token=tkn)
    ok(s == 200, f"wallet: {s}, balance={data.get('balance')}")

    # 重复注册应该失败
    s, _ = http("POST", "/api/train/register",
                body={"username": user, "password": pwd})
    ok(s in (400, 422), f"duplicate register rejected: {s}")

    # 错误密码
    s, _ = http("POST", "/api/train/login", body={"username": user, "password": "wrong"})
    ok(s == 401, f"wrong password rejected: {s}")

    # ---------- 2) 管理员生成兑换码 ----------
    step("2) 管理员登录 + 生成兑换码")
    s, data = http("POST", "/api/auth/login",
                    body={"username": "admin", "password": "admin123"})
    ok(s == 200, f"admin login: {s}")
    adm = data["data"]["access_token"]
    s, data = http("POST", "/api/train/admin/redeem-codes", token=adm,
                    body={"amount": 50000, "count": 2, "note": "test e2e"})
    ok(s == 200 and len(data.get("codes", [])) == 2, f"generate codes: {data}")
    code1 = data["codes"][0]
    code2 = data["codes"][1]
    s, data = http("GET", "/api/train/admin/redeem-codes", token=adm)
    ok(s == 200, f"list codes: {s}")

    # ---------- 3) 兑换码充值 ----------
    step("3) 兑换 + 二次使用应失败 + 错误码应报 404")
    s, data = http("POST", "/api/train/redeem", token=tkn,
                    body={"code": code1})
    ok(s == 200, f"redeem #1: {s}, got ¥{data.get('amount')}")
    s, data = http("GET", "/api/train/wallet", token=tkn)
    ok(data.get("balance") == 50000.0, f"balance after redeem: {data.get('balance')}")
    ok(data.get("total_topup") == 50000.0, f"total_topup: {data.get('total_topup')}")

    # 第二次使用同一码 → 应失败
    s, data = http("POST", "/api/train/redeem", token=tkn,
                    body={"code": code1})
    ok(s == 400, f"redeem same code rejected: {s}, {data.get('detail') or data.get('message')}")

    # 不存在的码
    s, data = http("POST", "/api/train/redeem", token=tkn,
                    body={"code": "NOTEXIST"})
    ok(s == 404, f"redeem unknown code: {s}")

    # ---------- 4) 余额不足 → 发起训练 ----------
    step("4) 余额不足应拒绝")

    # 创建一个临时穷鬼用户, 余额=0, 尝试发起训练
    poor = f"poor_{rand}"
    http("POST", "/api/train/register",
         body={"username": poor, "password": pwd})
    s, data = http("POST", "/api/train/login",
                    body={"username": poor, "password": pwd})
    poor_tkn = data["access_token"]
    s, data = http("POST", "/api/train/sessions/start", token=poor_tkn,
                    body={"start_date": "2024-01-01", "end_date": "2024-06-30",
                          "lookback_months": 3, "initial_cash": 500000,
                          "allow_split": True, "max_positions": 3,
                          "per_trade_amount": 50000})
    ok(s == 402, f"insufficient balance rejected: {s}, {data.get('detail') or data.get('message')}")

    # ---------- 5) 正常发起训练 ----------
    step("5) 发起训练 → 随机选股")
    s, data = http("POST", "/api/train/sessions/start", token=tkn,
                    body={"start_date": "2024-01-01", "end_date": "2024-06-30",
                          "lookback_months": 6, "initial_cash": 1000000,
                          "commission_rate": 0.0003, "min_commission": 5,
                          "stamp_tax": 0.001, "transfer_fee": 0.00001,
                          "allow_split": True, "max_positions": 3,
                          "per_trade_amount": 100000,
                          "allow_chinext": False, "allow_st": False,
                          "allow_kcb": False, "allow_bj": False})
    ok(s == 200, f"start session: {s}")
    sid = data["id"]
    code = data["code"]
    name = data["name"]
    print(f"   picked: {name}({code}) session_id={sid}")
    init_cash = data["initial_cash"]
    print(f"   revealed bars: {len(data['revealed_bars'])}, current={data['current_date']}")

    # 钱包余额已扣
    s, data = http("GET", "/api/train/wallet", token=tkn)
    ok(data["balance"] == 50000 - data["total_spent"],
       f"wallet balance updated: {data}")

    # ---------- 6) 推进 + K 线 ----------
    step("6) 时间推进 + K线 (daily/weekly/monthly)")
    s, data = http("POST", f"/api/train/sessions/{sid}/advance", token=tkn,
                    body={"days": 10})
    ok(s == 200, f"advance 10 days: {s}")
    cur_date = data["current_date"]
    print(f"   now at {cur_date}, bars={len(data['revealed_bars'])}")

    for period in ["daily", "weekly", "monthly"]:
        s, data = http("GET", f"/api/train/sessions/{sid}/kline",
                        token=tkn) if period == "daily" else \
                  http("GET", f"/api/train/sessions/{sid}/kline",
                        token=tkn)  # same path, use params below
        # The endpoint uses ?period=; urllib.request doesn't have a clean params arg here,
        # so we embed in URL
        pass

    # use proper query string
    import urllib.parse
    for period in ["daily", "weekly", "monthly"]:
        url = f"/api/train/sessions/{sid}/kline?period={period}"
        s, data = http("GET", url, token=tkn)
        cnt = len(data.get("items") or [])
        ok(s == 200, f"kline {period}: {s}, items={cnt}")

    # ---------- 7) 下单 ----------
    step("7) 买入 → 卖出 → 浮盈/已实现盈亏")
    # 用 100000 买入
    s, data = http("POST", f"/api/train/sessions/{sid}/trade", token=tkn,
                    body={"side": "BUY", "amount": 100000})
    ok(s == 200, f"buy 100000: {s}")
    pos = [p for p in data["positions"] if p["code"] == code]
    qty = pos[0]["quantity"] if pos else 0
    avg_cost = pos[0]["avg_cost"] if pos else 0
    print(f"   after buy -> positions qty={qty} avg_cost={avg_cost}")
    print(f"   cash={data['cash']} market_value={data['market_value']} "
          f"total={data['total_equity']} pnl={data['total_pnl']}")
    ok(qty > 0, "买入持仓 > 0")

    # 推进 5 天 (让价格波动)
    s, data = http("POST", f"/api/train/sessions/{sid}/advance", token=tkn,
                    body={"days": 5})
    ok(s == 200, f"advance 5 days: {s}")

    # 卖出全部
    s, data = http("POST", f"/api/train/sessions/{sid}/trade", token=tkn,
                    body={"side": "SELL", "quantity": qty})
    ok(s == 200, f"sell all {qty}: {s}")
    realized = data["recent_orders"][0].get("realized_pnl") or 0
    print(f"   realized_pnl={realized:.2f}")
    pos = [p for p in data["positions"] if p["code"] == code]
    ok((pos[0]["quantity"] if pos else 0) == 0, f"持仓清零")

    # ---------- 7b) 金额不足以买 1 手 ----------
    step("7b) 金额不足买 1 手")
    s, data = http("POST", f"/api/train/sessions/{sid}/trade", token=tkn,
                    body={"side": "BUY", "amount": 100})  # 只有 100 元
    ok(s == 400, f"amount too small rejected: {s}, {data.get('detail') or data.get('message')}")

    # ---------- 7c) 卖出超过持仓 ----------
    step("7c) 卖出超过持仓")
    s, data = http("POST", f"/api/train/sessions/{sid}/trade", token=tkn,
                    body={"side": "BUY", "amount": 100000})
    qty2 = [p for p in data["positions"] if p["code"] == code][0]["quantity"]
    s, data = http("POST", f"/api/train/sessions/{sid}/trade", token=tkn,
                    body={"side": "SELL", "quantity": qty2 + 100})
    ok(s == 400, f"oversell rejected: {s}, {data.get('detail') or data.get('message')}")

    # ---------- 8) 推进到上限 ----------
    step("8) 推进到终点")
    # 大力推进 250 天 (上限), 应该抵达最后一个 <= end_date 的交易日
    s, data = http("POST", f"/api/train/sessions/{sid}/advance", token=tkn,
                    body={"days": 250})
    ok(s == 200, f"advance 250 days: {s}, cur={data['current_date']}, end={data['end_date']}")
    cur = data["current_date"]
    end = data["end_date"]
    # 注意事项: end_date 不一定是交易日,如周末/节假日,所以只要 cur <= end 就 OK
    ok(cur <= end, f"current_date <= end_date: {cur} <= {end}")

    # 再推应该失败
    s, data = http("POST", f"/api/train/sessions/{sid}/advance", token=tkn,
                    body={"days": 1})
    ok(s == 400, f"advance past end rejected: {s}")

    # ---------- 9) 完成会话 ----------
    step("9) 完成会话 + 列表")
    s, data = http("POST", f"/api/train/sessions/{sid}/finish", token=tkn)
    ok(s == 200 and data["status"] == "finished", f"finish: {s}, status={data['status']}")

    # 完成后再推进 / 下单 应被拒绝
    s, _ = http("POST", f"/api/train/sessions/{sid}/advance", token=tkn,
                body={"days": 1})
    ok(s == 400, f"advance on finished rejected: {s}")

    s, _ = http("POST", f"/api/train/sessions/{sid}/trade", token=tkn,
                body={"side": "BUY", "amount": 100000})
    ok(s == 400, f"trade on finished rejected: {s}")

    # 列表
    s, data = http("GET", "/api/train/sessions", token=tkn)
    ok(s == 200 and len(data["items"]) > 0, f"sessions list: {s}, items={len(data['items'])}")
    statuses = [it["status"] for it in data["items"]]
    ok("finished" in statuses, f"finished in list: {statuses}")

    # ---------- 10) 鉴权隔离 ----------
    step("10) 鉴权隔离")
    # 用 admin token 访问训练端
    s, _ = http("GET", "/api/train/me", token=adm)
    ok(s == 401, f"admin token cannot access train/me: {s}")
    # 用 train token 访问管理员端
    s, _ = http("GET", "/api/stocks", token=tkn)
    ok(s == 401, f"train token cannot access stocks: {s}")

    # 不带 token
    s, _ = http("GET", "/api/train/me")
    ok(s == 401, f"no token rejected: {s}")

    # ---------- 11) 兑换码管理鉴权 ----------
    s, _ = http("POST", "/api/train/admin/redeem-codes", token=tkn,
                body={"amount": 1000, "count": 1})
    ok(s == 401, f"train token cannot create redeem codes: {s}")
    s, data = http("POST", "/api/train/admin/redeem-codes", token=adm,
                    body={"amount": 5000, "count": 1, "note": "extra"})
    ok(s == 200, f"admin creates code: {len(data.get('codes', []))}")

    print("\n--- E2E 测试完成 ---")


if __name__ == "__main__":
    main()
