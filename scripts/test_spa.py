"""前端 SPA 加载验证"""
import sys, re, requests
sys.stdout.reconfigure(encoding="utf-8")

s = requests.Session()
r = s.get("http://127.0.0.1:8000/")
print(f"GET /              = {r.status_code}")
print(f"  content-type     = {r.headers.get('content-type','')}")
print(f"  csp              = {r.headers.get('content-security-policy','')[:90]}")
print(f"  body[0:200]      = {r.text[:200]}")

m = re.search(r'src="\./assets/(index-[A-Za-z0-9_-]+\.js)"', r.text)
if m:
    js_url = f"http://127.0.0.1:8000/assets/{m.group(1)}"
    r2 = s.get(js_url)
    print(f"GET /assets/...    = {r2.status_code} | size={len(r2.content)}")
else:
    print("(no js asset found in index.html)")

for path in ["/train/home", "/admin/dashboard", "/admin/stocks"]:
    r3 = s.get(f"http://127.0.0.1:8000{path}")
    print(f"GET {path:24s} = {r3.status_code} (SPA fallback to index.html)")