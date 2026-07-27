"""
端到端 API 冒烟测试 - 直接用 requests 调后端
- 假设后端已运行在 http://127.0.0.1:8000
- 测试鉴权、cookie、限速、CSRF、业务接口
"""
import json
import sys
import time

import requests

# Windows console UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = "http://127.0.0.1:8000"
S = requests.Session()


def show(title, resp, body_keys=None):
    """统一打印: 状态码 + 关键字段"""
    short = resp.text[:300] if resp.text else "(empty)"
    try:
        j = resp.json()
        if body_keys:
            picked = {k: j.get(k) for k in body_keys}
            extra = json.dumps(picked, ensure_ascii=False)
        else:
            extra = json.dumps(j, ensure_ascii=False)[:240]
    except Exception:
        extra = short
    color = "[OK]" if 200 <= resp.status_code < 300 else "[FAIL]"
    print(f"{color} [{resp.status_code}] {title}  ->  {extra}")


def must(title, resp, expected_status, expect_keys=None):
    ok = resp.status_code == expected_status
    flag = "PASS" if ok else "FAIL"
    print(f"\n[{flag}] {title}")
    show("", resp, expect_keys)
    if not ok:
        print(f"  EXPECTED {expected_status}, GOT {resp.status_code}")
    return ok


def main() -> int:
    bad = 0
    s = requests.Session()

    # 0. 健康检查
    r = s.get(f"{BASE}/api/health", timeout=5)
    must("0. GET /api/health", r, 200, ["status", "app", "version"])
    bad += r.status_code != 200
    print("  security headers:")
    for h in ("x-content-type-options", "x-frame-options", "referrer-policy",
              "content-security-policy", "permissions-policy"):
        v = r.headers.get(h, "(missing)")
        print(f"    {h}: {v[:80]}{'...' if len(v) > 80 else ''}")

    # 1. 错误密码
    r = s.post(f"{BASE}/api/auth/login", json={"username": "ctt", "password": "wrong"})
    bad += not must("1. 错误密码 → 401 + 统一文案", r, 401, ["code", "message"])

    # 2. 正确密码登录
    r = s.post(f"{BASE}/api/auth/login", json={"username": "ctt", "password": "ctt584520"})
    bad += not must("2. ctt/ctt584520 登录 → 200", r, 200,
                    ["code", "access_token", "username", "csrf_token"])
    if r.status_code == 200:
        d = r.json().get("data", {})
        # 检查 cookie
        ck = s.cookies
        print(f"  cookies: {[c.name for c in ck]}")
        print(f"  must_change_pw: {d.get('must_change_pw')}")

    # 3. /api/auth/me (凭 cookie)
    r = s.get(f"{BASE}/api/auth/me")
    bad += not must("3. /api/auth/me (cookie 自动带)", r, 200, ["code", "username"])

    # 4. 伪造 Bearer token (期望 401)
    fake_s = requests.Session()
    fake_s.headers["Authorization"] = "Bearer fake.invalid.token"
    r = fake_s.get(f"{BASE}/api/auth/me")
    bad += not must("4. 伪造 Bearer → 401", r, 401)

    # 5. 训练端注册
    ts = int(time.time())
    train_user = f"smoke_{ts}"
    train_pwd = "abcd1234"
    r = s.post(f"{BASE}/api/train/register",
               json={"username": train_user, "password": train_pwd, "nickname": "smoke"})
    bad += not must(f"5. /api/train/register 用户 {train_user}", r, 200,
                    ["access_token", "user"])

    # 6. 训练端登录 (用一个新 session 隔离 cookie)
    s2 = requests.Session()
    r = s2.post(f"{BASE}/api/train/login",
                json={"username": train_user, "password": train_pwd})
    bad += not must(f"6. 训练端 {train_user} 登录", r, 200, ["access_token", "user_id"])
    # 把 token 写到 header,训练端依赖 Bearer
    if r.status_code == 200:
        token = r.json().get("data", {}).get("access_token") or r.json().get("access_token")
        if token:
            s2.headers["Authorization"] = f"Bearer {token}"

    # 7. 训练端 /me
    r = s2.get(f"{BASE}/api/train/me")
    bad += not must("7. /api/train/me (训练用户)", r, 200, ["username", "wallet_balance"])

    # 8. 训练端钱包
    r = s2.get(f"{BASE}/api/train/wallet")
    bad += not must("8. /api/train/wallet", r, 200, ["balance", "total_spent", "total_topup"])

    # 9. 业务:股票列表 (admin session)
    r = s.get(f"{BASE}/api/stocks", params={"page": 1, "page_size": 5})
    bad += not must("9. /api/stocks 列表", r, 200, ["total", "items"])

    # 10. 业务:系统状态
    r = s.get(f"{BASE}/api/system/status")
    bad += not must("10. /api/system/status", r, 200, ["tables"])

    # 11. 限速测试: 30 次错误登录(配置 20/minute, 期望最后若干个返回 429)
    print("\n[限速测试] 连发 30 次错误登录 (limit=20/min)")
    rate_s = requests.Session()
    hits_429 = 0
    hits_401 = 0
    for i in range(30):
        r = rate_s.post(f"{BASE}/api/auth/login",
                        json={"username": "ctt", "password": f"bad_pwd_{i}"})
        if r.status_code == 429:
            hits_429 += 1
        elif r.status_code == 401:
            hits_401 += 1
    print(f"  401 命中: {hits_401}, 429 命中: {hits_429}")
    if hits_429 > 0:
        print(f"  [OK] 限速生效: 至少 {hits_429} 次触发 429")
    else:
        print(f"  [FAIL] 限速未生效!")
        bad += 1

    # 12. CORS 预检
    r = requests.options(
        f"{BASE}/api/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    print("\nCORS 预检:")
    for k in ("Access-Control-Allow-Origin", "Access-Control-Allow-Credentials",
              "Access-Control-Allow-Methods", "Access-Control-Allow-Headers"):
        print(f"  {k}: {r.headers.get(k, '(missing)')}")
    bad += int(r.headers.get("Access-Control-Allow-Origin") != "http://localhost:5173")

    # 13. 异常脱敏
    r = s.get(f"{BASE}/api/stocks/nonexistent_code_xyz")
    print(f"\n[异常脱敏] (404): {r.status_code} -> {r.text[:200]}")
    if "error_id" in r.text:
        print("  [OK] 返回 error_id")
    else:
        print("  [FAIL] 缺少 error_id")
        bad += 1

    # 14. 训练端错误密码统一文案
    r = s2.post(f"{BASE}/api/train/login",
                json={"username": train_user, "password": "wrong_pwd"})
    bad += not must("14. 训练端错误密码 -> 401 统一文案", r, 401, ["code", "message"])
    msg = r.json().get("message", "")
    if "账号或密码错误" in msg:
        print(f"  [OK] 文案统一(无账号枚举): {msg}")
    else:
        print(f"  [FAIL] 文案可能泄漏: {msg}")
        bad += 1

    print(f"\n========== {'ALL PASSED' if bad == 0 else f'{bad} FAILURES'} ==========")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())