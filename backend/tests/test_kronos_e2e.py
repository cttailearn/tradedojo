"""Kronos E2E test — requires server running on :8000"""
import urllib.request, json, time, sys

BASE = "http://127.0.0.1:8000"
PASS = 0
FAIL = 0

def ok(msg):
    global PASS
    print(f"  PASS {msg}"); PASS += 1

def fail(msg):
    global FAIL
    print(f"  FAIL {msg}"); FAIL += 1

def api(token, method, path, body=None, timeout=180):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{BASE}{path}", data=data,
        headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"},
        method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def run():
    # login
    req = urllib.request.Request(f"{BASE}/api/auth/login",
        data=json.dumps({"username":"admin","password":"admin123"}).encode(),
        headers={"Content-Type":"application/json"}, method="POST")
    token = json.load(urllib.request.urlopen(req, timeout=10))["data"]["access_token"]
    ok("login")

    # 1. status
    s = api(token, "GET", "/api/kronos/status")
    assert s["available"] and len(s["models"]) >= 2
    ok(f"status: models={s['models']}")

    # 2. load
    t0 = time.time()
    s = api(token, "POST", "/api/kronos/load", {"model":"kronos-base","device":"cpu"})
    assert s["loaded"] and s["model_name"] == "kronos-base"
    ok(f"load: {time.time()-t0:.1f}s, device={s['device']}")

    # 3. simple predict (with extra model field)
    r = api(token, "POST", "/api/kronos/predict", {
        "code":"000001","lookback":100,"pred_len":10,"adjust":"qfq",
        "temperature":1.0,"top_p":0.9,"sample_count":1,
        "model":"kronos-base",
    })
    assert r["mode"] == "simple" and len(r["prediction"]) == 10
    ok(f"simple: pred={len(r['prediction'])}条")

    # 4. backtest (with extra model field)
    r = api(token, "POST", "/api/kronos/predict", {
        "code":"000001","lookback":120,"pred_len":20,"adjust":"qfq",
        "temperature":1.0,"top_p":0.9,"sample_count":1,
        "train_end":"2026-06-20","compare_actual":True,
        "model":"kronos-base",
    })
    assert r["mode"] == "backtest"
    m = r.get("metrics", {})
    ok(f"backtest: acc={m.get('direction_accuracy',0)}% MAE={m.get('mae',0):.4f}")

    # 5. 600519
    r = api(token, "POST", "/api/kronos/predict", {
        "code":"600519","lookback":120,"pred_len":15,"adjust":"qfq",
        "temperature":1.0,"top_p":0.9,"sample_count":1,
        "train_end":"2026-06-20","compare_actual":True,
    })
    assert r["mode"] == "backtest"
    ok(f"600519: metrics={r.get('metrics',{}).get('direction_accuracy','?')}%")

    # 6. SPA fallback
    for path in ["/", "/kronos"]:
        req = urllib.request.Request(f"{BASE}{path}")
        with urllib.request.urlopen(req, timeout=5) as r:
            assert b"<!DOCTYPE html>" in r.read()
            ok(f"SPA: {path} → {r.status}")

    print(f"\n{'='*40}")
    print(f"  {PASS} pass / {FAIL} fail ({PASS+FAIL} total)")
    print(f"{'='*40}")
    return FAIL == 0

if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
