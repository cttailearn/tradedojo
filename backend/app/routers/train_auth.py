"""
训练端用户注册/登录/钱包/兑换码 API
"""
import hashlib
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt

from app.config import settings
from app.deps import require_admin
from app.deps_train import get_current_train_user
from app.models import (
    RedeemRequest,
    RedeemCodeCreateRequest,
    TrainLoginRequest,
    TrainLoginResponse,
    TrainRegisterRequest,
    TrainUserInfo,
    WalletInfo,
)
from db.database import execute, get_conn, query_all, query_one


router = APIRouter(prefix="/api/train", tags=["训练端-用户"])


# ---------- helpers ----------
def _hash_pw(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                            salt.encode("utf-8"), 200_000)
    return h.hex(), salt


def _create_train_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": subject,
        "kind": "train",
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _get_or_create_wallet(user_id: int) -> dict:
    row = query_one(
        "SELECT balance, total_spent, total_topup FROM training_wallet WHERE user_id = ?",
        (user_id,),
    )
    if row is None:
        execute(
            "INSERT INTO training_wallet(user_id, balance, total_spent, total_topup) "
            "VALUES(?, 0, 0, 0)",
            (user_id,),
        )
        return {"balance": 0.0, "total_spent": 0.0, "total_topup": 0.0}
    return {"balance": float(row[0] or 0), "total_spent": float(row[1] or 0),
            "total_topup": float(row[2] or 0)}


# ---------- 注册 / 登录 ----------
@router.post("/register")
def register(payload: TrainRegisterRequest):
    username = (payload.username or "").strip()
    password = payload.password or ""
    if len(username) < 3 or len(username) > 32:
        raise HTTPException(status_code=400, detail="账号长度需 3-32 位")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码长度至少 6 位")
    if query_one("SELECT id FROM training_user WHERE username = ?", (username,)) is not None:
        raise HTTPException(status_code=400, detail="账号已存在")
    h, salt = _hash_pw(password)
    execute(
        "INSERT INTO training_user(username, password_hash, salt, display_name) "
        "VALUES(?, ?, ?, ?)",
        (username, h, salt, payload.display_name or username),
    )
    row = query_one("SELECT id FROM training_user WHERE username = ?", (username,))
    _get_or_create_wallet(row[0])
    return {"message": "注册成功", "username": username}


@router.post("/login")
def login(payload: TrainLoginRequest):
    row = query_one(
        "SELECT id, password_hash, salt, is_active, display_name "
        "FROM training_user WHERE username = ?",
        (payload.username,),
    )
    if not row:
        raise HTTPException(status_code=401, detail="账号或密码错误")
    if not row[3]:
        raise HTTPException(status_code=401, detail="账号已停用")
    h, _ = _hash_pw(payload.password, row[2])
    if not secrets.compare_digest(h, row[1]):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    token = _create_train_token(payload.username)
    execute(
        "UPDATE training_user SET last_login = datetime('now', 'localtime') WHERE id = ?",
        (row[0],),
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": payload.username,
        "user_id": row[0],
        "display_name": row[4],
    }


@router.get("/me")
def me(user: dict = Depends(get_current_train_user)):
    wallet = _get_or_create_wallet(user["id"])
    return {
        **user,
        "wallet": wallet,
    }


# ---------- 钱包 / 兑换码 ----------
@router.get("/wallet")
def wallet(user: dict = Depends(get_current_train_user)):
    return _get_or_create_wallet(user["id"])


@router.post("/redeem")
def redeem(payload: RedeemRequest, user: dict = Depends(get_current_train_user)):
    code = (payload.code or "").strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="请输入兑换码")

    with get_conn() as conn:
        row = conn.execute(
            "SELECT amount, is_used, used_by, COALESCE(revoked, 0) "
            "FROM redeem_code WHERE code = ?",
            (code,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="兑换码无效")
        if row[3]:
            raise HTTPException(status_code=400, detail="兑换码已作废")
        if row[1]:
            raise HTTPException(status_code=400, detail="兑换码已被使用")
        amount = float(row[0])
        # 原子操作:标记为已使用 + 给用户加余额
        conn.execute(
            "UPDATE redeem_code SET is_used = 1, used_by = ?, "
            "used_at = datetime('now', 'localtime') WHERE code = ? AND is_used = 0",
            (user["id"], code),
        )
        # 钱包 upsert
        wallet = conn.execute(
            "SELECT balance, total_topup FROM training_wallet WHERE user_id = ?",
            (user["id"],),
        ).fetchone()
        if wallet is None:
            conn.execute(
                "INSERT INTO training_wallet(user_id, balance, total_topup) VALUES(?, ?, ?)",
                (user["id"], amount, amount),
            )
        else:
            conn.execute(
                "UPDATE training_wallet SET balance = balance + ?, "
                "total_topup = total_topup + ?, "
                "updated_at = datetime('now', 'localtime') WHERE user_id = ?",
                (amount, amount, user["id"]),
            )
    return {"message": "兑换成功", "amount": amount, "code": code}


# ---------- 兑换码生成(管理员用,需要管理员 token) ----------
def _gen_code(amount: float, count: int, note: Optional[str], created_by: str):
    # 兑换码格式: 8 位随机 + 金额
    alphabet = string.ascii_uppercase + string.digits
    codes = []
    with get_conn() as conn:
        for _ in range(count):
            body = "".join(secrets.choice(alphabet) for _ in range(8))
            amount_part = f"{int(amount):08d}"
            code = f"{body}-{amount_part}"
            conn.execute(
                "INSERT INTO redeem_code(code, amount, created_by, note) VALUES(?, ?, ?, ?)",
                (code, amount, created_by, note),
            )
            codes.append(code)
    return codes


# 单独的"管理员"子路由,避免与训练端鉴权混在一起
admin_router = APIRouter(prefix="/api/train/admin", tags=["训练端-管理员"], dependencies=[Depends(require_admin)])


@admin_router.post("/redeem-codes")
def create_redeem_codes(payload: RedeemCodeCreateRequest, user: dict = Depends(require_admin)):
    """生成兑换码:需要管理员 token(同一份 admin 账号)"""
    codes = _gen_code(payload.amount, payload.count, payload.note, created_by=user["username"])
    return {"codes": codes, "count": len(codes), "amount": payload.amount}


@admin_router.get("/redeem-codes")
def list_redeem_codes(user: dict = Depends(require_admin)):
    rows = query_all(
        "SELECT code, amount, is_used, used_by, used_at, created_at, note "
        "FROM redeem_code ORDER BY created_at DESC LIMIT 200"
    )
    return {
        "items": [dict(zip(
            ["code", "amount", "is_used", "used_by", "used_at", "created_at", "note"], r
        )) for r in rows],
        "viewer": user["username"],
    }
