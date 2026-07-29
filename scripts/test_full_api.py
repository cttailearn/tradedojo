"""
项目功能综合测试 - 全量后端 API + 前端路由
- 不依赖特定账号,默认使用 ctt/ctt584520(已存在)
- 限速测试放在最后,避免污染主测试 session
- 输出 markdown 报告到 d:\\AI\\tradedojo\\TEST_REPORT.md
"""
import json
import sys
import time
from datetime import datetime
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = "http://127.0.0.1:8000"
ADMIN_USER = "ctt"
ADMIN_PASS = "ctt584520"

REPORT_PATH = r"d:\AI\tradedojo\TEST_REPORT.md"
results = []  # [(category, name, status_code, ok, detail)]


def add(category, name, ok, status, detail=""):
    results.append((category, name, status, ok, detail))
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {status:>4} | {category:<14} | {name}  {detail}")


def main():
    print(f"========== TradeDojo 综合测试 @ {datetime.now().isoformat(timespec='seconds')} ==========")

    s = requests.Session()

    # ---------- 健康检查 ----------
    try:
        r = s.get(f"{BASE}/api/health", timeout=5)
        add("system", "GET /api/health", r.status_code == 200, r.status_code,
            f"app={r.json().get('app')}, v={r.json().get('version')}")
    except Exception as e:
        add("system", "GET /api/health", False, 0, f"connect failed: {e}")
        return 1

    # ---------- 鉴权 ----------
    # 用 dedicated session 触发,避免 ctt 计数
    bad_s = requests.Session()
    r = bad_s.post(f"{BASE}/api/auth/login", json={"username": "ctt", "password": "wrong"})
    ok = r.status_code == 401 and ("账号或密码错误" in r.text or "错误" in r.text)
    add("auth", "错误密码 → 401 + 统一文案", ok, r.status_code)

    r = s.post(f"{BASE}/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS})
    ok = r.status_code == 200 and r.json().get("code") == 0
    add("auth", f"{ADMIN_USER} 登录 → 200", ok, r.status_code)

    # /auth/me
    r = s.get(f"{BASE}/api/auth/me")
    ok = r.status_code == 200 and r.json().get("data", {}).get("username") == ADMIN_USER
    add("auth", "GET /api/auth/me (cookie 鉴权)", ok, r.status_code)

    # 伪造 token
    fake = requests.Session()
    fake.headers["Authorization"] = "Bearer fake.invalid.token"
    r = fake.get(f"{BASE}/api/auth/me")
    add("auth", "伪造 Bearer → 401", r.status_code == 401, r.status_code)

    # 未授权访问
    r = requests.get(f"{BASE}/api/stocks")
    add("auth", "未登录 → 401 (deps)", r.status_code == 401, r.status_code)

    # ---------- 训练端 ----------
    ts = int(time.time())
    train_user = f"smokefull_{ts}"
    r = s.post(f"{BASE}/api/train/register",
               json={"username": train_user, "password": "abcd1234", "nickname": "smoke"})
    ok = r.status_code == 200 and "access_token" in r.text
    add("train", "POST /api/train/register", ok, r.status_code)

    s2 = requests.Session()
    r = s2.post(f"{BASE}/api/train/login",
                 json={"username": train_user, "password": "abcd1234"})
    ok = r.status_code == 200 and "access_token" in r.text
    add("train", "POST /api/train/login", ok, r.status_code)
    if ok:
        token = r.json().get("data", {}).get("access_token") or r.json().get("access_token")
        s2.headers["Authorization"] = f"Bearer {token}"

    for path, expected_keys in [
        ("/api/train/me", ["username", "wallet_balance"]),
        ("/api/train/wallet", ["balance", "total_spent", "total_topup"]),
    ]:
        r = s2.get(f"{BASE}{path}")
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        data = body.get("data", body)
        ok = r.status_code == 200 and all(k in data for k in expected_keys)
        add("train", f"GET {path}", ok, r.status_code)

    # ---------- 股票 (admin) ----------
    r = s.get(f"{BASE}/api/stocks", params={"page": 1, "page_size": 5})
    j = r.json().get("data", r.json())
    ok = r.status_code == 200 and "total" in j and len(j.get("items", [])) >= 1
    add("stocks", "GET /api/stocks (page=1)", ok, r.status_code,
        f"total={j.get('total')}, returned={len(j.get('items', []))}")

    # 关键词搜索
    r = s.get(f"{BASE}/api/stocks", params={"keyword": "平安", "page_size": 5})
    j = r.json().get("data", r.json())
    ok = r.status_code == 200 and j.get("total", 0) >= 1
    add("stocks", "GET /api/stocks?keyword=平安", ok, r.status_code,
        f"total={j.get('total')}")

    # 市场筛选
    r = s.get(f"{BASE}/api/stocks", params={"market": "sh", "page_size": 3})
    j = r.json().get("data", r.json())
    ok = r.status_code == 200
    items = j.get("items", [])
    all_sh = all(it.get("market") == "sh" for it in items)
    add("stocks", "GET /api/stocks?market=sh", ok and all_sh, r.status_code,
        f"total={j.get('total')}, all_sh={all_sh}")

    # 单股详情
    r = s.get(f"{BASE}/api/stocks/000001")
    body = r.json()
    # 接口返回扁平 dict(无 data 包装): 含 code 与 kline_count
    ok = r.status_code == 200 and "code" in body and body.get("code") == "000001"
    add("stocks", "GET /api/stocks/000001", ok, r.status_code,
        f"code={body.get('code')}, kline_count={body.get('kline_count')}")

    # 不存在的股票
    r = s.get(f"{BASE}/api/stocks/noexist")
    add("stocks", "GET /api/stocks/noexist → 404", r.status_code == 404, r.status_code)

    # ---------- K线 ----------
    r = s.get(f"{BASE}/api/kline", params={"code": "000001", "limit": 5})
    j = r.json().get("data", r.json())
    ok = r.status_code == 200 and "items" in j
    add("kline", "GET /api/kline?code=000001", ok, r.status_code,
        f"total={j.get('total')}, items={len(j.get('items', []))}")

    r = s.get(f"{BASE}/api/kline", params={"code": "000001", "start": "2026-01-01",
                                            "end": "2026-06-30", "limit": 100})
    add("kline", "GET /api/kline (date range)",
        r.status_code == 200, r.status_code)

    r = s.get(f"{BASE}/api/kline/indices", params={"code": "sh000001", "limit": 3})
    add("kline", "GET /api/kline/indices?code=sh000001",
        r.status_code == 200, r.status_code)

    # ---------- 系统状态 ----------
    r = s.get(f"{BASE}/api/system/status")
    j = r.json().get("data", r.json())
    ok = r.status_code == 200 and "tables" in j
    add("system", "GET /api/system/status", ok, r.status_code,
        f"tables={list(j.get('tables', {}).keys())}")

    r = s.get(f"{BASE}/api/system/check")
    add("system", "GET /api/system/check", r.status_code == 200, r.status_code)

    # ---------- CORS + 异常脱敏 ----------
    r = requests.options(f"{BASE}/api/auth/login", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    aco = r.headers.get("Access-Control-Allow-Origin", "")
    add("system", "CORS 预检 (Origin=localhost:5173)",
        "localhost:5173" in aco or aco == "*", 200 if aco else 0,
        f"acao={aco}")

    r = s.get(f"{BASE}/api/stocks/noexist")
    ok = "error_id" in r.text
    add("system", "异常脱敏 (error_id 字段)",
        ok, r.status_code, f"body[:80]={r.text[:80]}")

    # 安全响应头(在 /api/health 上确认)
    r = s.get(f"{BASE}/api/health")
    headers_check = {
        h: (h in r.headers) for h in ("x-content-type-options", "x-frame-options",
                                       "referrer-policy", "content-security-policy",
                                       "permissions-policy")
    }
    ok = sum(headers_check.values()) >= 4
    add("system", "安全响应头 (≥4/5 项)",
        ok, 200, f"got={sum(headers_check.values())}/5  [{', '.join(f'{k}={v}' for k,v in headers_check.items())}]")

    # ---------- 前端资源 ----------
    for path in ("/", "/login", "/admin", "/train", "/train/login",
                 "/dashboard", "/stocks", "/kline", "/backtest", "/tasks",
                 "/scheduler", "/sources", "/system", "/strategies",
                 "/train/stats", "/train/report"):
        rr = requests.get(f"{BASE}{path}", allow_redirects=False)
        ok = rr.status_code == 200 and "<title>" in rr.text
        add("frontend", f"GET {path}", ok, rr.status_code)

    # 静态资产
    r = requests.get(f"{BASE}/assets/index-Bwmnp8S0.js", allow_redirects=False)
    add("frontend", "GET /assets/*.js (chunk)",
        r.status_code == 200, r.status_code)

    # ---------- 限速 (放最后, dedicated session) ----------
    rate_s = requests.Session()
    h429, h401 = 0, 0
    for i in range(25):
        rr = rate_s.post(f"{BASE}/api/auth/login",
                          json={"username": "ctt", "password": f"bad_{i}"})
        if rr.status_code == 429: h429 += 1
        elif rr.status_code == 401: h401 += 1
    add("system", "限速: 25 次错误登录 (限速 10/min)",
        h429 > 0, 200 if h429 == 0 else 429, f"401={h401}, 429={h429}")

    # ---------- 汇总 ----------
    passed = sum(1 for _, _, _, ok, _ in results if ok)
    failed = sum(1 for _, _, _, ok, _ in results if not ok)
    print(f"\n========== {passed} PASS / {failed} FAIL / {len(results)} TOTAL ==========")

    # 生成 Markdown 报告
    lines = [f"# TradeDojo 项目功能测试报告", ""]
    lines.append(f"- 报告时间: `{datetime.now().isoformat(timespec='seconds')}`")
    lines.append(f"- 后端地址: `http://127.0.0.1:8000`")
    lines.append(f"- 运行模式: `STOCK_DEV=1`(开发模式)")
    lines.append("")
    lines.append("## 汇总")
    lines.append("")
    lines.append(f"- 通过: **{passed}**")
    lines.append(f"- 失败: **{failed}**")
    lines.append(f"- 总数: **{len(results)}**")
    lines.append("")
    lines.append("## 详细结果")
    lines.append("")
    lines.append("| 类别 | 用例 | 状态 | HTTP | 备注 |")
    lines.append("|------|------|------|------|------|")
    for cat, name, code, ok, det in results:
        flag = "✅" if ok else "❌"
        # 避免 | 破坏 markdown 表格
        det_safe = det.replace("|", "\\|")
        lines.append(f"| {cat} | {name} | {flag} | {code} | {det_safe} |")
    lines.append("")
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n>> Markdown 报告写入: {REPORT_PATH}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
