"""CSRF / refresh token / change-password 流验证"""
import sys, requests
sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
BASE = "http://127.0.0.1:8000"

# 登录拿 cookie
r = s.post(f"{BASE}/api/auth/login", json={"username": "ctt", "password": "ctt584520"})
print(f"[1] login                  = {r.status_code}")
assert r.status_code == 200, r.text
csrf = s.cookies.get("tdj_csrf", "")
assert csrf, "tdj_csrf cookie 缺失"
print(f"    csrf cookie            = {csrf[:24]}...")

# 1. 写操作不带 CSRF(用 cookie 模式)
r = s.post(f"{BASE}/api/auth/change-password",
           json={"old_password": "ctt584520", "new_password": "ctt584520"})
print(f"[2] change-pw 无 CSRF      = {r.status_code} (期望 403)")
assert r.status_code == 403, r.text

# 2. 写操作带错误 CSRF
r = s.post(f"{BASE}/api/auth/change-password",
           json={"old_password": "ctt584520", "new_password": "ctt584520"},
           headers={"X-CSRF-Token": "wrong_token"})
print(f"[3] change-pw 错 CSRF      = {r.status_code} (期望 403)")
assert r.status_code == 403, r.text

# 3. 写操作带正确 CSRF(把密码改成临时值再改回)
r = s.post(f"{BASE}/api/auth/change-password",
           json={"old_password": "ctt584520", "new_password": "TmpP@ss_2026"},
           headers={"X-CSRF-Token": csrf})
print(f"[4] change-pw 正确 CSRF    = {r.status_code} (期望 200)")
assert r.status_code == 200, r.text

# 4. 改密后旧 session 应该被踢下线(cookie 被清,refresh 被吊销)
r = s.get(f"{BASE}/api/auth/me")
print(f"[5] /me 旧 cookie (改密后) = {r.status_code} (期望 401 - 立即踢下线)")
assert r.status_code == 401

# 5. refresh endpoint 应当失败(被吊销)
r = s.post(f"{BASE}/api/auth/refresh")
print(f"[6] refresh 旧 token       = {r.status_code} (期望 401 已吊销)")
assert r.status_code == 401

# 6. 用新密码登录拿新 token
s2 = requests.Session()
r = s2.post(f"{BASE}/api/auth/login",
            json={"username": "ctt", "password": "TmpP@ss_2026"})
print(f"[7] 新密码登录             = {r.status_code}")
assert r.status_code == 200

# 7. 把密码改回
csrf2 = s2.cookies.get("tdj_csrf", "")
r = s2.post(f"{BASE}/api/auth/change-password",
            json={"old_password": "TmpP@ss_2026", "new_password": "ctt584520"},
            headers={"X-CSRF-Token": csrf2})
print(f"[8] 密码改回 ctt584520    = {r.status_code} (期望 200)")
assert r.status_code == 200, r.text

print("\n[OK] CSRF + refresh 吊销 + 改密流全部通过")