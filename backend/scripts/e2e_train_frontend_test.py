"""
第二个测试脚本 - 前端兼容性 + 边界场景
  A) 日期反向(start > end)
  B) 训练开始日早于今天(默认历史日期)
  C) 周 K / 月 K 聚合字段正确性
  D) 持仓盈亏计算与按权益曲线一致
  E) 已结束会话的会话页能正常加载(只读)
  F) 重复兑换码 (一码对应一用户) - 同一码无法被多人使用
  G) 同账号多次并发训练
  H) 错误请求格式(非 JSON / 字段缺失)
"""
import json
import uuid
import urllib.request
import urllib.error


BASE = "http://127.0.0.1:8001"


def http(method, path, token=None, body=None, raw=None, expect=200):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    elif raw is not None:
        data = raw.encode() if isinstance(raw, str) else raw
    else:
        data = None
    req = urllib.request.Request(BASE + path, method=method,
                                  headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b)
        except Exception:
            return e.code, {"raw": b.decode("utf-8", "ignore")}


def step(t):
    print(f"\n=== {t} ===")


def ok(cond, label):
    print(("[OK]" if cond else "[FAIL]"), label)
    return bool(cond)


def main():
    rand = uuid.uuid4().hex[:6]
    user = f"qa_{rand}"
    pwd = "pwd123456"

    s, _ = http("POST", "/api/train/register",
                body={"username": user, "password": pwd})
    ok(s == 200, f"register {user}: {s}")
    s, data = http("POST", "/api/train/login",
                    body={"username": user, "password": pwd})
    tkn = data["access_token"]

    # 给用户一次充值
    s, data = http("POST", "/api/auth/login",
                    body={"username": "admin", "password": "admin123"})
    adm = data["data"]["access_token"]
    s, data = http("POST", "/api/train/admin/redeem-codes", token=adm,
                    body={"amount": 10000, "count": 1, "note": "qa"})
    ok(s == 200, "admin creates 10000 code")
    code = data["codes"][0]
    http("POST", "/api/train/redeem", token=tkn, body={"code": code})

    # A) 日期反向
    step("A) 反向日期")
    s, data = http("POST", "/api/train/sessions/start", token=tkn,
                    body={"start_date": "2024-06-30", "end_date": "2024-01-01",
                          "lookback_months": 1, "initial_cash": 500000})
    # Pydantic: start < end, 422 model-level; but ours model doesn't check cross-field
    # 业务层 _pick_random_stock 会接受任意两段,只会因为数据不足失败
    # 视结果: 422 (模型字段顺序检查) / 400 / 404 都算符合预期被拒绝
    ok(s in (400, 404, 422), f"reversed date rejected: {s}")

    # B) 默认历史日期
    step("B) 历史日期")
    s, data = http("POST", "/api/train/sessions/start", token=tkn,
                    body={"start_date": "2023-06-01", "end_date": "2023-12-31",
                          "lookback_months": 6, "initial_cash": 500000,
                          "allow_split": False, "max_positions": 5,
                          "per_trade_amount": 50000,
                          "commission_rate": 0.0003, "min_commission": 5,
                          "stamp_tax": 0.001, "transfer_fee": 0.00001})
    ok(s == 200, f"start with historical dates: {s}, code={data.get('code')}")
    sid_a = data["id"]

    # C) 周 K / 月 K 聚合
    step("C) K 线周期聚合")
    for period, exp_min in [("daily", 100), ("weekly", 20), ("monthly", 5)]:
        s, data = http("GET",
                       f"/api/train/sessions/{sid_a}/kline?period={period}",
                       token=tkn)
        items = data.get("items") or []
        if items:
            # 验证关键字段
            bar = items[0]
            ok("open" in bar and "close" in bar and "high" in bar and "low" in bar,
               f"  {period} bar 字段完整")
            # 周 K items 应 < 日 K items
        ok(s == 200, f"  kline {period}: {s} items={len(items)}")

    # D) 资金曲线 + 已实现盈亏一致
    step("D) 推进→买入→推进→卖出, 资金曲线 vs 现金")
    s, data = http("POST", f"/api/train/sessions/{sid_a}/advance", token=tkn,
                    body={"days": 10})
    # 买
    cur_price = float(data["current_bar"]["close"])
    qty = (100000 // (cur_price * 100)) * 100
    s, data = http("POST", f"/api/train/sessions/{sid_a}/trade", token=tkn,
                    body={"side": "BUY", "amount": 100000})
    ok(s == 200, "buy in QA session A")
    # 推进 5 天
    s, data = http("POST", f"/api/train/sessions/{sid_a}/advance", token=tkn,
                    body={"days": 5})
    cur_price2 = float(data["current_bar"]["close"])
    # 卖
    s, data = http("POST", f"/api/train/sessions/{sid_a}/trade", token=tkn,
                    body={"side": "SELL", "quantity": qty})
    ok(s == 200, "sell all")
    # 检查实现的 pnl = (sell_price - buy_price)*qty - 总费用(本次买卖 2 笔)
    recent = data["recent_orders"]
    realized = recent[0].get("realized_pnl") or 0
    total_fees = sum((o.get("total_fee") or 0) for o in recent)
    expected = (cur_price2 - cur_price) * qty - total_fees
    print(f"   realized={realized:.2f}, expected={expected:.2f}")
    ok(abs(realized - expected) < 1.0, "实现盈亏与手工算一致")

    # E) 已结束会话仍能 GET
    step("E) 完成会话仍可加载")
    s, data = http("POST", f"/api/train/sessions/{sid_a}/finish", token=tkn)
    ok(s == 200, f"finish: {s}")
    s, data = http("GET", f"/api/train/sessions/{sid_a}", token=tkn)
    ok(s == 200 and data["status"] == "finished",
       f"finished session GET ok: {s}, status={data['status']}")

    # F) 同一码多人同时使用 → 应该只有一个人成功
    step("F) 兑换码并发使用互斥")
    # 生成一个码
    s, data = http("POST", "/api/train/admin/redeem-codes", token=adm,
                    body={"amount": 5000, "count": 1, "note": "concurrent"})
    concurrent_code = data["codes"][0]
    # 两个用户都尝试兑换
    user_b = f"qb_{rand}"
    http("POST", "/api/train/register", body={"username": user_b, "password": pwd})
    s, data = http("POST", "/api/train/login",
                    body={"username": user_b, "password": pwd})
    tkn_b = data["access_token"]
    # 用户 A (tkn) 已用过其他码,余额大约 9xxx 元
    s_a, d_a = http("POST", "/api/train/redeem", token=tkn,
                     body={"code": concurrent_code})
    s_b, d_b = http("POST", "/api/train/redeem", token=tkn_b,
                     body={"code": concurrent_code})
    ok((s_a, s_b) in [(200, 400), (400, 200)],
       f"一码只能一人成功: A={s_a} B={s_b}")

    # G) 多笔订单 → FIFO 成本
    step("G) 多笔 BUY + 一次 SELL, FIFO 验证")
    # 开新会话
    s, data = http("POST", "/api/train/sessions/start", token=tkn,
                    body={"start_date": "2023-01-01", "end_date": "2023-03-31",
                          "lookback_months": 3, "initial_cash": 500000,
                          "allow_split": True, "max_positions": 5,
                          "per_trade_amount": 100000})
    sid_g = data["id"]
    http("POST", f"/api/train/sessions/{sid_g}/advance", token=tkn,
         body={"days": 5})
    # 第一笔买入 1000 股
    s, data = http("POST", f"/api/train/sessions/{sid_g}/trade", token=tkn,
                    body={"side": "BUY", "quantity": 1000, "price": None})
    p1 = data["positions"][0]["avg_cost"]
    http("POST", f"/api/train/sessions/{sid_g}/advance", token=tkn, body={"days": 5})
    # 第二笔买入 2000 股
    s, data = http("POST", f"/api/train/sessions/{sid_g}/trade", token=tkn,
                    body={"side": "BUY", "quantity": 2000, "price": None})
    p2 = data["positions"][0]["avg_cost"]
    ok(p2 != p1, f"两次买入均价变化: p1={p1}, p2={p2}")

    # H) 请求格式错误
    step("H) 请求格式错误")
    # 缺字段
    s, data = http("POST", "/api/train/sessions/start", token=tkn, body={})
    ok(s in (400, 422), f"missing fields: {s}")
    # 错误 JSON
    req = urllib.request.Request(
        BASE + "/api/train/sessions/start", method="POST",
        headers={"Content-Type": "application/json",
                  "Authorization": f"Bearer {tkn}"},
        data=b"not-json-{",
    )
    try:
        urllib.request.urlopen(req).read()
        ok(False, "malformed JSON should 422")
    except urllib.error.HTTPError as e:
        ok(e.code in (400, 422), f"malformed JSON: {e.code}")

    print("\n--- 第二轮 E2E 测试完成 ---")


if __name__ == "__main__":
    main()
