"""
训练端·管理员后台
- 用户管理(列表/详情/停用启用/重置密码)
- 资金管理(手动加减余额 + 必有原因)
- 兑换码管理(列出 + 作废)
- 操作日志(所有写操作都进 admin_action_log)

鉴权:全部 require_admin (admin 的 JWT,kind != 'train')
"""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config import settings
from app.deps import require_admin
from app.deps_train import _hash_pw
from app.models import (
    AdminActionLogResponse,
    AdjustWalletRequest,
    RedeemCodeDetailResponse,
    RedeemCodeCreateRequest,
    ResetUserPasswordRequest,
    RevokeRedeemCodeRequest,
    SetUserActiveRequest,
    TrainingUserDetailResponse,
)
from db.database import (
    user_execute as execute,
    get_user_conn as get_conn,
    user_query_all as query_all,
    user_query_one as query_one,
)

router = APIRouter(
    prefix="/api/train/admin",
    tags=["训练端-管理员后台"],
    dependencies=[Depends(require_admin)],
)


# =========================================================
# helpers
# =========================================================
def _log_action(
    *,
    actor: str,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    detail: Optional[dict] = None,
    reason: str = "",
    before: Optional[str] = None,
    after: Optional[str] = None,
) -> None:
    """通用:写一条审计日志。失败不抛(审计失败不应该影响主业务)。"""
    try:
        execute(
            "INSERT INTO admin_action_log(actor, action, target_type, target_id, "
            "detail_json, reason, before_value, after_value) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (
                actor,
                action,
                target_type,
                target_id,
                json.dumps(detail, ensure_ascii=False) if detail is not None else None,
                reason,
                before,
                after,
            ),
        )
    except Exception as e:
        # 审计失败只能吞了 —— 主业务优先
        print(f"[admin_action_log] write failed: {e}")


def _get_wallet(user_id: int) -> dict:
    row = query_one(
        "SELECT balance, total_spent, total_topup FROM training_wallet WHERE user_id = ?",
        (user_id,),
    )
    if row is None:
        return {"balance": 0.0, "total_spent": 0.0, "total_topup": 0.0,
                "user_id": user_id, "exists": False}
    return {
        "user_id": user_id,
        "exists": True,
        "balance": float(row[0] or 0),
        "total_spent": float(row[1] or 0),
        "total_topup": float(row[2] or 0),
    }


# =========================================================
# 用户管理
# =========================================================
@router.get("/users")
def list_users(
    search: Optional[str] = Query(None, description="按用户名/昵称模糊搜"),
    is_active: Optional[int] = Query(None, description="1=启用, 0=停用, null=全部"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """训练用户列表(带钱包)"""
    where = []
    params = []
    if search:
        where.append("(u.username LIKE ? OR u.display_name LIKE ?)")
        s = f"%{search}%"
        params.extend([s, s])
    if is_active is not None:
        where.append("u.is_active = ?")
        params.append(is_active)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    sql = f"""
        SELECT u.id, u.username, u.display_name, u.is_active, u.created_at, u.last_login,
               w.balance, w.total_spent, w.total_topup
        FROM training_user u
        LEFT JOIN training_wallet w ON w.user_id = u.id
        {where_sql}
        ORDER BY u.id DESC LIMIT ? OFFSET ?
    """
    rows = query_all(sql, (*params, limit, offset))
    items = []
    for r in rows:
        items.append({
            "id": r[0],
            "username": r[1],
            "display_name": r[2],
            "is_active": r[3],
            "created_at": r[4],
            "last_login": r[5],
            "wallet": {
                "balance": float(r[6] or 0),
                "total_spent": float(r[7] or 0),
                "total_topup": float(r[8] or 0),
                "exists": r[6] is not None,
            },
        })

    total = query_one(
        f"SELECT COUNT(*) FROM training_user u {where_sql}",
        tuple(params),
    )[0]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/users/{user_id}", response_model=TrainingUserDetailResponse)
def get_user(user_id: int):
    row = query_one(
        "SELECT id, username, display_name, is_active, created_at, last_login "
        "FROM training_user WHERE id = ?",
        (user_id,),
    )
    if row is None:
        raise HTTPException(404, "用户不存在")
    return {
        "id": row[0],
        "username": row[1],
        "display_name": row[2],
        "is_active": row[3],
        "created_at": row[4],
        "last_login": row[5],
        "wallet": _get_wallet(user_id),
    }


@router.post("/users/{user_id}/set-active")
def set_user_active(
    user_id: int,
    payload: SetUserActiveRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    row = query_one(
        "SELECT username, is_active FROM training_user WHERE id = ?",
        (user_id,),
    )
    if not row:
        raise HTTPException(404, "用户不存在")
    target_username = row[0]
    before_active = int(row[1])
    after_active = 1 if payload.is_active else 0
    if before_active == after_active:
        return {"ok": True, "noop": True,
                "is_active": before_active,
                "username": target_username}

    execute("UPDATE training_user SET is_active = ? WHERE id = ?",
             (after_active, user_id))
    # 停用用户时, 同时下线该用户的全部 token
    if after_active == 0:
        try:
            execute(
                "CREATE TABLE IF NOT EXISTS train_token("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  user_id INTEGER NOT NULL,"
                "  token TEXT UNIQUE NOT NULL,"
                "  expires_at TEXT NOT NULL,"
                "  created_at TEXT DEFAULT (datetime('now', 'localtime'))"
                ")"
            )
            execute("DELETE FROM train_token WHERE user_id = ?", (user_id,))
        except Exception:
            pass

    _log_action(
        actor=user["username"],
        action="set_user_active",
        target_type="user",
        target_id=str(user_id),
        reason=payload.reason,
        before=str(before_active),
        after=str(after_active),
        detail={"target_username": target_username,
                "ip": request.client.host if request.client else None},
    )
    return {"ok": True, "is_active": after_active, "username": target_username}


@router.post("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    payload: ResetUserPasswordRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """管理员重置密码(用户登录被踢,下次登录要重新登录)"""
    row = query_one(
        "SELECT username, display_name FROM training_user WHERE id = ?",
        (user_id,),
    )
    if not row:
        raise HTTPException(404, "用户不存在")
    h = _hash_pw(payload.new_password)
    execute(
        "UPDATE training_user SET password_hash = ?, salt = '' WHERE id = ?",
        (h, user_id),
    )
    # 强制下线该用户的所有 session (train_token)
    try:
        execute(
            "CREATE TABLE IF NOT EXISTS train_token("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  user_id INTEGER NOT NULL,"
            "  token TEXT UNIQUE NOT NULL,"
            "  expires_at TEXT NOT NULL,"
            "  created_at TEXT DEFAULT (datetime('now', 'localtime'))"
            ")"
        )
        execute("DELETE FROM train_token WHERE user_id = ?", (user_id,))
    except Exception:
        pass
    _log_action(
        actor=user["username"],
        action="reset_user_password",
        target_type="user",
        target_id=str(user_id),
        reason=payload.reason,
        detail={"target_username": row[0],
                "ip": request.client.host if request.client else None},
    )
    return {"ok": True, "username": row[0]}


# =========================================================
# 资金管理
# =========================================================
@router.post("/users/{user_id}/adjust-wallet")
def adjust_wallet(
    user_id: int,
    payload: AdjustWalletRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """加扣余额:
       - delta > 0 加款
       - delta < 0 扣款
       - adjust_topup=True 时:同步更新 total_topup(模拟"再发一张兑换码"或"补发退款")
       - adjust_topup=False(默认):加款增加 topup,扣款增加 spent —— 业务上不会反向
    """
    if abs(payload.delta) < 0.01:
        raise HTTPException(400, "delta 不能接近 0")

    row = query_one("SELECT username FROM training_user WHERE id = ?", (user_id,))
    if not row:
        raise HTTPException(404, "用户不存在")
    target_username = row[0]

    before = _get_wallet(user_id)
    if not before["exists"]:
        execute(
            "INSERT INTO training_wallet(user_id, balance, total_spent, total_topup) "
            "VALUES(?, 0, 0, 0)",
            (user_id,),
        )

    new_balance = round(before["balance"] + payload.delta, 2)
    if new_balance < 0:
        raise HTTPException(
            400,
            f"扣款会导致余额变负:现余额 ¥{before['balance']:.2f},扣款 ¥{payload.delta:.2f}",
        )

    with get_conn() as conn:
        if payload.adjust_topup:
            new_topup = round(before["total_topup"] + payload.delta, 2)
            conn.execute(
                "UPDATE training_wallet SET balance = ?, "
                "total_topup = total_topup + ?, "
                "updated_at = datetime('now', 'localtime') "
                "WHERE user_id = ?",
                (new_balance, payload.delta, user_id),
            )
        else:
            if payload.delta > 0:
                conn.execute(
                    "UPDATE training_wallet SET balance = balance + ?, "
                    "total_topup = total_topup + ?, "
                    "updated_at = datetime('now', 'localtime') "
                    "WHERE user_id = ?",
                    (payload.delta, payload.delta, user_id),
                )
            else:
                conn.execute(
                    "UPDATE training_wallet SET balance = balance + ?, "
                    "total_spent = total_spent + ?, "
                    "updated_at = datetime('now', 'localtime') "
                    "WHERE user_id = ?",
                    (payload.delta, -payload.delta, user_id),
                )

    after = _get_wallet(user_id)
    _log_action(
        actor=user["username"],
        action="adjust_wallet",
        target_type="user",
        target_id=str(user_id),
        reason=payload.reason,
        before=json.dumps({"balance": before["balance"],
                            "total_topup": before["total_topup"],
                            "total_spent": before["total_spent"]},
                           ensure_ascii=False),
        after=json.dumps({"balance": after["balance"],
                          "total_topup": after["total_topup"],
                          "total_spent": after["total_spent"]},
                         ensure_ascii=False),
        detail={"target_username": target_username,
                "delta": payload.delta,
                "adjust_topup": payload.adjust_topup,
                "ip": request.client.host if request.client else None},
    )
    return {
        "ok": True,
        "username": target_username,
        "before_balance": before["balance"],
        "after_balance": after["balance"],
        "delta": payload.delta,
    }


# =========================================================
# 兑换码管理
# =========================================================
@router.get("/redeem-codes")
def list_redeem_codes(
    is_used: Optional[int] = Query(None),
    revoked: Optional[int] = Query(None, description="0=正常,1=已作废,null=全部"),
    created_by: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="按码段搜"),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """列出兑换码(分页+过滤)"""
    where = ["1=1"]
    params = []
    # 新版 schema 加了 revoked 列(用 0/1 取代删码,我们用 ALTER)
    try:
        is_used_val = is_used
        if is_used_val is not None:
            where.append("is_used = ?")
            params.append(is_used_val)
        if revoked is not None:
            where.append("COALESCE(revoked, 0) = ?")
            params.append(revoked)
        if created_by:
            where.append("created_by = ?")
            params.append(created_by)
        if search:
            where.append("code LIKE ?")
            params.append(f"%{search}%")
        sql = (
            "SELECT code, amount, is_used, used_by, used_at, created_by, note, "
            "created_at, COALESCE(revoked, 0) AS revoked "
            "FROM redeem_code WHERE " + " AND ".join(where) +
            " ORDER BY created_at DESC, code LIMIT ? OFFSET ?"
        )
        rows = query_all(sql, (*params, limit, offset))
        # 拼 used_by_username
        user_ids = {r[3] for r in rows if r[3] is not None}
        username_map = {}
        if user_ids:
            for u in query_all(
                "SELECT id, username FROM training_user WHERE id IN (%s)"
                % ",".join("?" * len(user_ids)),
                tuple(user_ids),
            ):
                username_map[u[0]] = u[1]
        items = [{
            "code": r[0], "amount": float(r[1]),
            "is_used": int(r[2]), "used_by": r[3], "used_at": r[4],
            "used_by_username": username_map.get(r[3]),
            "created_by": r[5], "note": r[6], "created_at": r[7],
            "revoked": int(r[8]),
        } for r in rows]
        total = query_one(
            "SELECT COUNT(*) FROM redeem_code WHERE " + " AND ".join(where),
            tuple(params),
        )[0]
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        # 旧版 DB 没 revoked 列时,降级
        if "no such column" not in str(e):
            raise
        sql = (
            "SELECT code, amount, is_used, used_by, used_at, created_by, note, "
            "created_at FROM redeem_code WHERE " + " AND ".join(where) +
            " ORDER BY created_at DESC, code LIMIT ? OFFSET ?"
        )
        rows = query_all(sql, (*params, limit, offset))
        user_ids = {r[3] for r in rows if r[3] is not None}
        username_map = {}
        if user_ids:
            for u in query_all(
                "SELECT id, username FROM training_user WHERE id IN (%s)"
                % ",".join("?" * len(user_ids)),
                tuple(user_ids),
            ):
                username_map[u[0]] = u[1]
        items = [{
            "code": r[0], "amount": float(r[1]),
            "is_used": int(r[2]), "used_by": r[3], "used_at": r[4],
            "used_by_username": username_map.get(r[3]),
            "created_by": r[5], "note": r[6], "created_at": r[7],
            "revoked": 0,
        } for r in rows]
        total = query_one(
            "SELECT COUNT(*) FROM redeem_code WHERE " + " AND ".join(where),
            tuple(params),
        )[0]
        return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/redeem-codes")
def create_redeem_codes(
    payload: RedeemCodeCreateRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """生成兑换码"""
    import secrets
    import string

    alphabet = string.ascii_uppercase + string.digits
    codes = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_conn() as conn:
        for _ in range(payload.count):
            body = "".join(secrets.choice(alphabet) for _ in range(8))
            amount_part = f"{int(payload.amount):08d}"
            code = f"{body}-{amount_part}"
            conn.execute(
                "INSERT INTO redeem_code(code, amount, created_by, note, created_at) "
                "VALUES(?, ?, ?, ?, ?)",
                (code, payload.amount, user["username"], payload.note, now),
            )
            codes.append(code)

    _log_action(
        actor=user["username"],
        action="create_redeem_codes",
        target_type="redeem_code",
        target_id=None,
        reason=payload.note or "",
        detail={"amount": payload.amount, "count": len(codes),
                "codes": codes,
                "ip": request.client.host if request.client else None},
    )
    return {"codes": codes, "count": len(codes), "amount": payload.amount}


@router.post("/redeem-codes/{code}/revoke")
def revoke_redeem_code(
    code: str,
    payload: RevokeRedeemCodeRequest,
    request: Request,
    user: dict = Depends(require_admin),
):
    """作废未使用的兑换码(已使用的不允许作废 —— 退钱走 adjust_wallet)"""
    code = code.strip().upper()
    row = query_one(
        "SELECT is_used, COALESCE(revoked, 0) FROM redeem_code WHERE code = ?",
        (code,),
    )
    if not row:
        raise HTTPException(404, "兑换码不存在")
    if int(row[0]):
        raise HTTPException(400, "兑换码已使用,请走 adjust_wallet 给用户退款")

    # 旧 DB 无 revoked 列 -> 先 ALTER
    with get_conn() as conn:
        try:
            conn.execute("SELECT revoked FROM redeem_code LIMIT 1")
        except Exception:
            conn.execute("ALTER TABLE redeem_code ADD COLUMN revoked INTEGER DEFAULT 0")

        cur_revoked = conn.execute(
            "SELECT COALESCE(revoked, 0) FROM redeem_code WHERE code = ?",
            (code,),
        ).fetchone()
        if cur_revoked and int(cur_revoked[0]):
            return {"ok": True, "noop": True, "code": code}
        conn.execute(
            "UPDATE redeem_code SET revoked = 1 WHERE code = ?",
            (code,),
        )

    _log_action(
        actor=user["username"],
        action="revoke_redeem_code",
        target_type="redeem_code",
        target_id=code,
        reason=payload.reason,
        before="0", after="1",
        detail={"ip": request.client.host if request.client else None},
    )
    return {"ok": True, "code": code, "revoked": True}


# =========================================================
# 审计
# =========================================================
@router.get("/action-log", response_model=AdminActionLogResponse)
def list_action_log(
    actor: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    target_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """管理员操作审计日志(所有人/所有操作可查)"""
    where = ["1=1"]
    params = []
    if actor:
        where.append("actor = ?")
        params.append(actor)
    if action:
        where.append("action = ?")
        params.append(action)
    if target_type:
        where.append("target_type = ?")
        params.append(target_type)
    if target_id:
        where.append("target_id = ?")
        params.append(target_id)
    sql = (
        "SELECT id, actor, actor_kind, action, target_type, target_id, "
        "detail_json, reason, before_value, after_value, created_at "
        "FROM admin_action_log WHERE " + " AND ".join(where) +
        " ORDER BY id DESC LIMIT ? OFFSET ?"
    )
    rows = query_all(sql, (*params, limit, offset))
    items = [{
        "id": r[0], "actor": r[1], "actor_kind": r[2], "action": r[3],
        "target_type": r[4], "target_id": r[5],
        "detail_json": r[6], "reason": r[7],
        "before_value": r[8], "after_value": r[9],
        "created_at": r[10],
    } for r in rows]
    total = query_one(
        "SELECT COUNT(*) FROM admin_action_log WHERE " + " AND ".join(where),
        tuple(params),
    )[0]
    return {"items": items, "total": total}
