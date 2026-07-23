"""
E2E: 训练端管理员后台
 - 注册普通训练用户 + 充值
 - admin 端:列出用户,启用/停用,重置密码
 - admin 端:加扣余额(必须 reason)、超扣拦截、写审计日志
 - admin 端:作废未使用的兑换码,作废已使用的失败,使用已作废失败
 - 用户端:已停用账号登录被拒
 - 越权:普通训练用户 / 训练端 admin 端拒绝访问
 - 操作日志可查
"""
import json
import secrets
import string
import time
import uuid
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8001"


def http(method, path, token=None, body=None, raw=None, expect=None):
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
    user = f"qaadm_{rand}"
    pwd = "pwd123456"

    # 1) 注册一个普通训练用户(用来验证 /admin/* 全是越权)
    http("POST", "/api/train/register", body={"username": user, "password": pwd, "display_name": "测试"})
    s, data = http("POST", "/api/train/login", body={"username": user, "password": pwd})
    user_tkn = data["access_token"]
    user_uid = data["user_id"]
    ok(True, f"普通用户 {user} 注册登录 uid={user_uid}")

    # 2) admin 登录
    s, data = http("POST", "/api/auth/login", body={"username": "admin", "password": "admin123"})
    admin_tkn = data["data"]["access_token"]
    ok(True, "admin 登录")

    # ----- A. 鉴权:训练 token 进不了 admin -----
    step("A) 鉴权隔离")
    s, _ = http("GET", "/api/train/admin/users", token=user_tkn)
    ok(s == 401, f"训练 token 进 /admin/users 被拒 ({s})")
    s, _ = http("GET", "/api/train/admin/users", )
    ok(s == 401, f"无 token 进 /admin/users 被拒 ({s})")

    # ----- B. 列出用户,可以看到刚注册的 -----
    step("B) 用户列表")
    s, data = http("GET", "/api/train/admin/users?search=" + user, token=admin_tkn)
    ok(s == 200, f"users list: {s}")
    items = data.get("items") or []
    target = next((x for x in items if x["username"] == user), None)
    ok(target is not None, f"找到刚注册用户 {user}")
    uid = target["id"]
    initial_balance = float(target["wallet"]["balance"])

    # ----- C. 调整钱包:加款 -----
    step("C) 调整钱包 (加款)")
    s, data = http("POST", f"/api/train/admin/users/{uid}/adjust-wallet",
                    token=admin_tkn,
                    body={"delta": 10000, "reason": "测试 - 加款 100 元", "adjust_topup": False})
    ok(s == 200, f"加款: {s}")
    # 复查
    s, data = http("GET", f"/api/train/admin/users/{uid}", token=admin_tkn)
    bal = float(data["wallet"]["balance"])
    ok(abs(bal - (initial_balance + 10000)) < 0.01,
       f"余额正确 ({initial_balance} -> {bal})")

    # ----- D. 调整钱包:扣款 -----
    step("D) 调整钱包 (扣款)")
    s, data = http("POST", f"/api/train/admin/users/{uid}/adjust-wallet",
                    token=admin_tkn,
                    body={"delta": -5000, "reason": "测试 - 扣款 50 元", "adjust_topup": False})
    ok(s == 200, f"扣款: {s}")

    # ----- E. 必须带 reason -----
    step("E) 缺 reason 必拒")
    s, _ = http("POST", f"/api/train/admin/users/{uid}/adjust-wallet",
                token=admin_tkn,
                body={"delta": 1, "reason": ""})
    ok(s == 422, f"缺 reason 被拒: {s}")

    # ----- F. 超扣拦截 -----
    step("F) 超扣拦截 (不允许变负)")
    s, data = http("POST", f"/api/train/admin/users/{uid}/adjust-wallet",
                    token=admin_tkn,
                    body={"delta": -99999999, "reason": "测 - 不应被允许"})
    ok(s == 400, f"超扣被拒: {s}")
    print(f"   detail: ok") if data.get('detail') else print("   detail: err")

    # ----- G. delta=0 拒 -----
    step("G) delta=0 被拒")
    s, data = http("POST", f"/api/train/admin/users/{uid}/adjust-wallet",
                    token=admin_tkn,
                    body={"delta": 0, "reason": "应该拒掉"})
    ok(s in (400, 422), f"delta=0 被拒: {s}")

    # ----- H. 停用账号 + 用户登录被拒 -----
    step("H) 停用账号 → 用户登录被拒")
    s, data = http("POST", f"/api/train/admin/users/{uid}/set-active",
                    token=admin_tkn,
                    body={"is_active": False, "reason": "测试 - 停用"})
    ok(s == 200, f"停用接口: {s}")
    s, data = http("POST", "/api/train/login", body={"username": user, "password": pwd})
    ok(s == 401, f"停用账号登录被拒: {s}, detail={data.get('detail')}")
    # 启用回来
    s, data = http("POST", f"/api/train/admin/users/{uid}/set-active",
                    token=admin_tkn,
                    body={"is_active": True, "reason": "测完用回来"})
    ok(s == 200, f"重新启用: {s}")
    s, data = http("POST", "/api/train/login", body={"username": user, "password": pwd})
    ok(s == 200, f"启用后能登: {s}")

    # ----- I. 重置密码 -----
    step("I) 重置密码")
    new_pwd = "NewPwd_" + rand
    s, data = http("POST", f"/api/train/admin/users/{uid}/reset-password",
                    token=admin_tkn,
                    body={"new_password": new_pwd, "reason": "测 - 重置"})
    ok(s == 200, f"reset 接口: {s}")
    # 旧密码不能登
    s, _ = http("POST", "/api/train/login", body={"username": user, "password": pwd})
    ok(s == 401, f"旧密码登不上: {s}")
    # 新密码可以登
    s, data = http("POST", "/api/train/login", body={"username": user, "password": new_pwd})
    ok(s == 200, f"新密码登入: {s}")

    # ----- J. 兑换码生成 + 作废 -----
    step("J) 兑换码: 生成 → 作废 → 用户用已作废失败 → 列表可见 revoked")
    s, data = http("POST", "/api/train/admin/redeem-codes",
                    token=admin_tkn,
                    body={"amount": 12345, "count": 3, "note": "QA-作废测"})
    ok(s == 200, f"生成 3 张: {s}")
    code_ok, code_used, code_orphan = data["codes"]
    # 让用户用掉一张
    s, data = http("POST", "/api/train/redeem", token=user_tkn, body={"code": code_used})
    ok(s == 200, f"用户成功用掉一张: {s}")
    # 作废"未使用"那张
    s, data = http("POST", f"/api/train/admin/redeem-codes/{code_orphan}/revoke",
                    token=admin_tkn, body={"reason": "测 - 作废未使用"})
    ok(s == 200, f"作废未使用码成功: {s}")
    # 已使用的码作废 - 应失败
    s, data = http("POST", f"/api/train/admin/redeem-codes/{code_used}/revoke",
                    token=admin_tkn, body={"reason": "测 - 应失败"})
    ok(s == 400, f"作废已使用码应被拒: {s}, detail={data.get('detail')}")
    # 用户尝试用已作废码 - 应失败
    s, data = http("POST", "/api/train/redeem", token=user_tkn, body={"code": code_orphan})
    ok(s == 400, f"用户用已作废码被拒: {s}, detail={data.get('detail')}")
    # 但正常的那张 code_ok 用户仍能用
    s, data = http("POST", "/api/train/redeem", token=user_tkn, body={"code": code_ok})
    ok(s == 200, f"用户用第三张未受影响: {s}")

    # ----- K. 兑换码列表带过滤 -----
    step("K) 兑换码列表过滤")
    s, data = http("GET", f"/api/train/admin/redeem-codes?search={code_used}&revoked=0",
                    token=admin_tkn)
    ok(s == 200, f"按搜索: {s}")
    ok(any(c["code"] == code_used for c in data["items"]), "搜索能找到已使用的码")
    s, data = http("GET", f"/api/train/admin/redeem-codes?revoked=1",
                    token=admin_tkn)
    ok(s == 200, f"查已作废: {s}")
    ok(any(c["code"] == code_orphan and c["revoked"] == 1 for c in data["items"]),
       "列表能找到作废那张")

    # ----- L. 操作日志 -----
    step("L) 操作日志查得到")
    s, data = http("GET", "/api/train/admin/action-log?limit=200", token=admin_tkn)
    ok(s == 200, f"action log: {s}")
    actions = [l["action"] for l in data["items"]]
    for required in ["adjust_wallet", "set_user_active", "reset_user_password",
                     "create_redeem_codes", "revoke_redeem_code"]:
        ok(required in actions, f"log 含动作: {required}")
    # 可按动作过滤
    s, data = http("GET", "/api/train/admin/action-log?action=adjust_wallet",
                    token=admin_tkn)
    ok(s == 200 and all(l["action"] == "adjust_wallet" for l in data["items"]),
       "action=adjust_wallet 过滤生效")

    # ----- M. 训练用户进 action-log 也被拒 -----
    step("M) 训练 token 拿不到日志")
    s, _ = http("GET", "/api/train/admin/action-log", token=user_tkn)
    ok(s == 401, f"训练 token 被拒: {s}")

    print("\n--- admin 后台 E2E 完成 ---")


if __name__ == "__main__":
    main()
