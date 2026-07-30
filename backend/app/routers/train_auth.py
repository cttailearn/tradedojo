"""
训练用户认证 / 注册 / 登录 / 兑换

P0 加固:
- 注册/登录/兑换全部限速
- 错误文案统一(防账号枚举);停用账号也是"账号或密码错误"
- 拒绝明文密码(老数据要求重置)
- 注册时不打印密码哈希
- 兑换成功不泄漏码面值是否过大
"""
import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Query
from pydantic import BaseModel, Field, field_validator

from app.auth import create_access_token
from app.config import settings
from app.deps_train import get_current_train_user
from app.rate_limit import limiter
from db.database import (
    user_execute as execute,
    get_user_conn as get_conn,
    user_query_all as query_all,
    user_query_one as query_one,
)


log = logging.getLogger("app.train.auth")
router = APIRouter(prefix="/api/train", tags=["训练端-认证"])


# =========================================================
# 密码哈希 (PBKDF2-HMAC-SHA256) - 拒绝明文
# =========================================================
PBKDF2_ITER = 200_000
HASH_ALGO = "sha256"
SALT_BYTES = 16
HASH_BYTES = 32


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    h = hashlib.pbkdf2_hmac(HASH_ALGO, password.encode("utf-8"), salt, PBKDF2_ITER, dklen=HASH_BYTES)
    return f"pbkdf2_{HASH_ALGO}${PBKDF2_ITER}${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str, legacy_salt: str = "") -> bool:
    """
    仅接受 PBKDF2 格式(以及旧的"分列 hash+salt"格式,会自动迁移)。
    拒绝明文比对: 一律视为校验失败。
    """
    if not stored:
        return False
    if stored.startswith(f"pbkdf2_{HASH_ALGO}$"):
        try:
            _, iter_str, salt_hex, hash_hex = stored.split("$", 3)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(hash_hex)
            actual = hashlib.pbkdf2_hmac(
                HASH_ALGO, password.encode("utf-8"), salt, int(iter_str), dklen=len(expected),
            )
            return hmac.compare_digest(expected, actual)
        except Exception:
            return False
    if legacy_salt:
        # 旧格式兼容: hash(hex) + salt 列
        try:
            expected = bytes.fromhex(stored)
            actual = hashlib.pbkdf2_hmac(
                HASH_ALGO, password.encode("utf-8"),
                legacy_salt.encode("utf-8"), PBKDF2_ITER, dklen=len(expected),
            )
            return hmac.compare_digest(expected, actual)
        except Exception:
            return False
    # 明文 → 视为失败(强制迁移路径:下次登录会自动写新 hash,但仍需校验通过)
    return False


USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")
RESERVED_NAMES = {"admin", "root", "system", "test", "guest", "operator", "null", "undefined", "anonymous"}


def _check_username(name: str) -> str | None:
    if not USERNAME_RE.match(name):
        return "账号只能包含字母/数字/下划线/点/连字符, 长度 3-32"
    if name.lower() in RESERVED_NAMES:
        return "该账号名已被系统保留, 请使用其他名称"
    return None


class RegisterReq(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=64)
    nickname: str = Field("", max_length=32)

    @field_validator("username")
    @classmethod
    def _v_username(cls, v: str) -> str:
        err = _check_username(v)
        if err:
            raise ValueError(err)
        return v

    @field_validator("password")
    @classmethod
    def _v_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码至少 8 位")
        if v.isdigit() or v.isalpha():
            raise ValueError("密码必须包含字母和数字的组合")
        return v


class LoginReq(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class ChangePwReq(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=64)

    @field_validator("new_password")
    @classmethod
    def _v(cls, v: str) -> str:
        if v.isdigit() or v.isalpha():
            raise ValueError("新密码必须包含字母和数字的组合")
        return v


class RedeemReq(BaseModel):
    code: str = Field(..., min_length=8, max_length=64)


# =========================================================
# Token 记录
# =========================================================
TOKEN_TTL_DAYS = 7
TOKEN_BYTES = 32


def _ensure_token_table() -> None:
    execute(
        "CREATE TABLE IF NOT EXISTS train_token("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  user_id INTEGER NOT NULL,"
        "  token TEXT UNIQUE NOT NULL,"
        "  expires_at TEXT NOT NULL,"
        "  created_at TEXT DEFAULT (datetime('now', 'localtime'))"
        ")"
    )


def _issue_token(user_id: int) -> str:
    """签发训练端 JWT(短 token,供 get_current_train_user 校验)"""
    return create_access_token(subject=str(user_id), extra={"kind": "train"})


def _record_token(user_id: int, jti: str) -> None:
    _ensure_token_table()
    expires = (datetime.now() + timedelta(days=TOKEN_TTL_DAYS)).isoformat(timespec="seconds")
    execute(
        "INSERT INTO train_token(user_id, token, expires_at) VALUES(?, ?, ?)",
        (user_id, jti, expires),
    )


# =========================================================
# API
# =========================================================
def _generic_auth_error():
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="账号或密码错误",
    )


@router.post("/register")
@limiter.limit(settings.REGISTER_RATE_LIMIT)
def register(req: RegisterReq, request: Request, response: Response):
    """注册(限速 + 强度校验 + 用户名保留字)"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM training_user WHERE username = ?", (req.username,)
        ).fetchone()
        if row:
            raise HTTPException(status_code=409, detail="账号已存在")
        pw_hash = hash_password(req.password)
        cur = conn.execute(
            "INSERT INTO training_user(username, password_hash, salt, display_name, is_active) "
            "VALUES(?, ?, ?, ?, 1)",
            (req.username, pw_hash, "", req.nickname or req.username),
        )
        uid = cur.lastrowid
        conn.execute(
            "INSERT INTO training_wallet(user_id, balance) VALUES(?, 0)", (uid,)
        )
    token = _issue_token(uid)
    return {
        "access_token": token,
        "token": token,
        "user": {"id": uid, "username": req.username, "nickname": req.nickname or req.username},
    }


@router.post("/login")
@limiter.limit(settings.LOGIN_RATE_LIMIT)
def login(req: LoginReq, request: Request, response: Response):
    """登录(限速 + 错误文案统一)"""
    row = query_one(
        "SELECT id, username, display_name, password_hash, salt, is_active "
        "FROM training_user WHERE username = ?",
        (req.username,),
    )
    if not row:
        log.info("[TRAIN-LOGIN] 用户不存在 username=%s", req.username)
        _generic_auth_error()
    uid, username, display_name, stored_hash, salt, is_active = row
    # is_active 单独告知? 否,统一文案
    if not is_active:
        log.info("[TRAIN-LOGIN] 账号停用 username=%s", req.username)
        _generic_auth_error()
    if not verify_password(req.password, stored_hash, salt):
        _generic_auth_error()
    # 自动迁移旧格式到新格式
    if not stored_hash.startswith(f"pbkdf2_{HASH_ALGO}$"):
        try:
            execute(
                "UPDATE training_user SET password_hash = ?, salt = '' WHERE id = ?",
                (hash_password(req.password), uid),
            )
        except Exception as e:
            log.warning("迁移训练用户密码失败: %s", e)
    execute(
        "UPDATE training_user SET last_login = datetime('now','localtime') WHERE id = ?",
        (uid,),
    )
    token = _issue_token(uid)
    return {
        "access_token": token,
        "token": token,
        "user_id": uid,
        "username": username,
        "display_name": display_name or username,
        "user": {"id": uid, "username": username, "nickname": display_name or username},
    }


@router.post("/logout")
def logout(user: dict = Depends(get_current_train_user)):
    _ensure_token_table()
    execute("DELETE FROM train_token WHERE user_id = ?", (user["id"],))
    return {"message": "已登出"}


@router.get("/me")
def me(user: dict = Depends(get_current_train_user)):
    row = query_one(
        "SELECT username, display_name, created_at, last_login "
        "FROM training_user WHERE id = ?", (user["id"],),
    )
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    balance = query_one(
        "SELECT balance FROM training_wallet WHERE user_id = ?", (user["id"],)
    )
    balance_val = float(balance[0] or 0) if balance else 0.0
    return {
        "id": user["id"],
        "username": row[0],
        "nickname": row[1] or row[0],
        "display_name": row[1] or row[0],
        "created_at": row[2],
        "last_login": row[3],
        "wallet_balance": balance_val,
        "wallet": {
            "balance": balance_val,
            "total_spent": 0.0,
            "total_topup": 0.0,
        },
    }


@router.get("/wallet")
def get_wallet(user: dict = Depends(get_current_train_user)):
    row = query_one(
        "SELECT balance, total_spent, total_topup, updated_at "
        "FROM training_wallet WHERE user_id = ?", (user["id"],),
    )
    if not row:
        return {"balance": 0.0, "total_spent": 0.0, "total_topup": 0.0, "updated_at": None}
    balance, total_spent, total_topup, updated_at = row
    return {
        "balance": float(balance or 0),
        "total_spent": float(total_spent or 0),
        "total_topup": float(total_topup or 0),
        "updated_at": updated_at,
    }


@router.post("/change-password")
def change_password(req: ChangePwReq, user: dict = Depends(get_current_train_user)):
    row = query_one(
        "SELECT password_hash, salt FROM training_user WHERE id = ?", (user["id"],)
    )
    if not row or not verify_password(req.old_password, row[0], row[1] or ""):
        raise HTTPException(status_code=401, detail="原密码错误")
    if req.old_password == req.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")
    execute(
        "UPDATE training_user SET password_hash = ?, salt = '' WHERE id = ?",
        (hash_password(req.new_password), user["id"]),
    )
    _ensure_token_table()
    execute("DELETE FROM train_token WHERE user_id = ?", (user["id"],))
    return {"message": "密码已修改, 请重新登录"}


@router.post("/redeem")
@limiter.limit(settings.LOGIN_RATE_LIMIT)
def redeem(req: RedeemReq, request: Request, response: Response, user: dict = Depends(get_current_train_user)):
    """兑换码充值(原子化)"""
    code = req.code.strip()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT amount, is_used, used_by, revoked "
            "FROM redeem_code WHERE code = ?", (code,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="兑换码不存在")
        amount, is_used, used_by, revoked = row
        if revoked:
            raise HTTPException(status_code=400, detail="兑换码已被作废")
        if is_used or used_by is not None:
            raise HTTPException(status_code=400, detail="兑换码已被使用")
        now = datetime.now().isoformat(timespec="seconds")
        cur = conn.execute(
            "UPDATE redeem_code SET is_used = 1, used_by = ?, used_at = ? "
            "WHERE code = ? AND is_used = 0 AND used_by IS NULL AND revoked = 0",
            (user["id"], now, code),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=400, detail="兑换码已被他人使用")
        conn.execute(
            "INSERT INTO training_wallet(user_id, balance) VALUES(?, 0) "
            "ON CONFLICT(user_id) DO NOTHING", (user["id"],),
        )
        conn.execute(
            "UPDATE training_wallet SET balance = balance + ?, "
            "total_topup = total_topup + ?, "
            "updated_at = datetime('now','localtime') WHERE user_id = ?",
            (amount, amount, user["id"]),
        )
    balance = query_one(
        "SELECT balance FROM training_wallet WHERE user_id = ?", (user["id"],)
    )[0] or 0
    return {"message": "充值成功", "amount": amount, "balance": float(balance)}


@router.get("/topup-logs")
def topup_logs(
    user: dict = Depends(get_current_train_user),
    limit: int = Query(50, ge=1, le=200),
):
    row = query_one(
        "SELECT balance, total_spent, total_topup, updated_at "
        "FROM training_wallet WHERE user_id = ?", (user["id"],),
    )
    if not row:
        return {"items": [], "summary": {"balance": 0, "total_spent": 0, "total_topup": 0}}
    balance, total_spent, total_topup, updated_at = row
    return {
        "items": [],
        "summary": {
            "balance": float(balance or 0),
            "total_spent": float(total_spent or 0),
            "total_topup": float(total_topup or 0),
            "updated_at": updated_at,
        },
    }