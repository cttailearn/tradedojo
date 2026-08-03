"""
训练用户认证 / 注册 / 登录 / 兑换

P0 加固:
- 注册/登录/兑换全部限速
- 错误文案统一(防账号枚举);停用账号也是"账号或密码错误"
- 拒绝明文密码(老数据要求重置)
- 注册时不打印密码哈希
- 兑换成功不泄漏码面值是否过大

P0-1 修复 (2026-07-31): 训练端 access token 改用 httpOnly cookie
P0-2 修复 (2026-07-31): 训练端 refresh 机制
  - access 短(默认 12h) + refresh 长(7d) 双 token
  - /api/train/refresh 端点支持旋转 + DB 吊销
  - train_token 表加 revoked / refresh_jti 列
"""
import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Query
from jose import JWTError
from pydantic import BaseModel, Field, field_validator

from app.auth import (
    clear_train_cookies,
    create_access_token,
    decode_token,
    fingerprint_for,
    is_refresh_revoked,
    issue_token_pair,
    refresh_jti_from_payload,
    rotate_refresh,
    set_train_cookies,
)
from app.config import settings
from app.deps_train import get_current_train_user
from app.rate_limit import limiter
from db.database import (
    user_execute as execute,
    get_user_conn as get_conn,
    user_query_all as query_all,
    user_query_one as query_one,
    is_postgres,
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
# Token 记录 (2026-07-31 P0-2: 加 refresh 旋转 + 吊销)
# =========================================================
TOKEN_TTL_DAYS = 7


def _ensure_token_table() -> None:
    """建表 + 老库兼容补列 (revoked / refresh_jti)"""
    if not is_postgres:
        # SQLite:内联 DDL 惰性建表;PG 下 train_token 已由 schema_pg.sql 创建,
        # 且 INTEGER PRIMARY KEY AUTOINCREMENT 是 SQLite 专有语法,PG 无法解析
        execute(
            "CREATE TABLE IF NOT EXISTS train_token("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  user_id INTEGER NOT NULL,"
            "  token TEXT UNIQUE NOT NULL,"
            "  refresh_jti TEXT,"
            "  expires_at TEXT NOT NULL,"
            "  revoked INTEGER DEFAULT 0,"
            "  created_at TEXT DEFAULT (datetime('now', 'localtime'))"
            ")"
        )
    # 老库兼容:补列(PG 下列已存在,探测后跳过)
    for col_def, col_name in (
        ("refresh_jti TEXT", "refresh_jti"),
        ("revoked INTEGER DEFAULT 0", "revoked"),
    ):
        try:
            execute(f"SELECT {col_name} FROM train_token LIMIT 1")
        except Exception:
            execute(f"ALTER TABLE train_token ADD COLUMN {col_def}")


def _ensure_login_lock_columns() -> None:
    """老库兼容:training_user 补登录锁定列(SQLite/PG 老库自动 ALTER)。

    注意:不能用 execute() 探测列(user_execute 吞异常,探测失败不抛,
    补列永不执行)。改用列名清单判断:
    - SQLite: PRAGMA table_info(表不存在返回空,不抛)
    - PG:     information_schema.columns
    """
    try:
        if is_postgres:
            rows = query_all(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'training_user'"
            )
            cols = {r[0] for r in rows} if rows else set()
        else:
            rows = query_all("PRAGMA table_info(training_user)")
            cols = {r[1] for r in rows} if rows else set()
    except Exception:
        return
    for col_def, col_name in (
        ("last_failed_login TEXT", "last_failed_login"),
        ("failed_attempts INTEGER DEFAULT 0", "failed_attempts"),
    ):
        if col_name not in cols:
            execute(f"ALTER TABLE training_user ADD COLUMN {col_def}")


# =========================================================
# 登录失败锁定 (2026-08-03: 防暴力破解, 与管理端同策略)
# =========================================================
LOCK_MAX_ATTEMPTS = 5
LOCK_WINDOW_MINUTES = 15


def _is_train_user_locked(
    last_failed_login: Optional[str], failed_attempts: Optional[int],
) -> bool:
    """账号锁定判断: 失败次数 >= 阈值, 且最近一次失败仍在窗口内。"""
    if not failed_attempts or failed_attempts < LOCK_MAX_ATTEMPTS:
        return False
    if not last_failed_login:
        return False
    try:
        # PG 老数据可能是 'YYYY-MM-DD HH:MM:SS'(空格分隔),
        # Python 3.10 的 fromisoformat 只接受 'T' 分隔, 统一替换
        dt = datetime.fromisoformat(last_failed_login.replace(" ", "T"))
        return datetime.now() - dt < timedelta(minutes=LOCK_WINDOW_MINUTES)
    except Exception:
        return False


def _record_failed_login(uid: int) -> None:
    try:
        # COALESCE: PG 老库 ALTER 补列后存量行值为 NULL,NULL+1 仍是 NULL
        # (SQLite 的 NULL+1 同理),显式按 0 起计
        # 时间戳由 Python 生成(本地时区),与 _is_train_user_locked 里
        # datetime.now() 同基准 —— 不能用 SQL datetime('now','localtime'):
        # PG 容器时区(UTC)与本地(UTC+8)不一致会导致窗口判断永远失败
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        execute(
            "UPDATE training_user SET failed_attempts = COALESCE(failed_attempts, 0) + 1, "
            "last_failed_login = ? WHERE id = ?",
            (now, uid),
        )
    except Exception as e:
        log.warning("记录训练用户登录失败失败: %s", e)


def _clear_failed_login(uid: int) -> None:
    try:
        execute(
            "UPDATE training_user SET failed_attempts = 0, "
            "last_failed_login = NULL WHERE id = ?",
            (uid,),
        )
    except Exception as e:
        log.warning("清零训练用户登录失败计数失败: %s", e)


def _issue_train_token_pair(
    user_id: int,
    request: Optional[Request] = None,
) -> tuple[str, str, str, str]:
    """签发训练端 access + refresh 双 token (P0-2 修复)。

    返回 (access, refresh, access_jti, refresh_jti)。
    access 绑定客户端指纹(防 XSS/中间人偷走 token 后跨浏览器使用)。
    """
    fp = fingerprint_for(request) if request else None
    access = create_access_token(
        subject=str(user_id),
        extra={"kind": "train"},
        fingerprint=fp,
        token_type="access",
    )
    refresh = create_access_token(
        subject=str(user_id),
        extra={"kind": "train"},
        token_type="refresh",
    )
    access_jti = refresh_jti_from_payload(access)  # 取 access jti
    refresh_jti = refresh_jti_from_payload(refresh)
    return access, refresh, access_jti, refresh_jti


def _record_token(
    user_id: int,
    access_jti: str,
    refresh_jti: Optional[str] = None,
    ttl_days: int = TOKEN_TTL_DAYS,
) -> None:
    _ensure_token_table()
    expires = (
        datetime.now(timezone.utc) + timedelta(days=ttl_days)
    ).isoformat(timespec="seconds")
    execute(
        "INSERT INTO train_token(user_id, token, refresh_jti, expires_at) "
        "VALUES(?, ?, ?, ?)",
        (user_id, access_jti, refresh_jti, expires),
    )


def _revoke_token(jti: str) -> None:
    _ensure_token_table()
    execute("UPDATE train_token SET revoked = 1 WHERE token = ?", (jti,))


def _revoke_refresh(jti: str) -> None:
    _ensure_token_table()
    execute("UPDATE train_token SET revoked = 1 WHERE refresh_jti = ?", (jti,))


def _revoke_all_for(user_id: int) -> None:
    _ensure_token_table()
    execute("UPDATE train_token SET revoked = 1 WHERE user_id = ?", (user_id,))


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
    # 2026-07-31 P0-1 修复: cookie 模式签发 token
    access, refresh, ajti, rjti = _issue_train_token_pair(uid, request)
    _record_token(uid, ajti, rjti)
    set_train_cookies(response, access, refresh)
    return {
        "access_token": access,  # 兼容旧调用(老前端 Bearer)
        "token": access,
        "user": {"id": uid, "username": req.username, "nickname": req.nickname or req.username},
    }


@router.post("/login")
@limiter.limit(settings.LOGIN_RATE_LIMIT)
def login(req: LoginReq, request: Request, response: Response):
    """登录(限速 + 失败锁定 + 错误文案统一 + 2026-07-31 改 cookie 模式)"""
    _ensure_login_lock_columns()
    row = query_one(
        "SELECT id, username, display_name, password_hash, salt, is_active, "
        "last_failed_login, failed_attempts "
        "FROM training_user WHERE username = ?",
        (req.username,),
    )
    if not row:
        log.info("[TRAIN-LOGIN] 用户不存在 username=%s", req.username)
        _generic_auth_error()
    uid, username, display_name, stored_hash, salt, is_active, last_failed, attempts = row
    # is_active 单独告知? 否,统一文案
    if not is_active:
        log.info("[TRAIN-LOGIN] 账号停用 username=%s", req.username)
        _generic_auth_error()
    # 防暴力破解: 账号级失败锁定 (2026-08-03, 与管理端同策略)
    if _is_train_user_locked(last_failed, attempts):
        log.warning("[TRAIN-LOGIN] 账号已锁定 username=%s", req.username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试次数过多, 请稍后再试",
        )
    if not verify_password(req.password, stored_hash, salt):
        _record_failed_login(uid)
        log.info("[TRAIN-LOGIN] 密码错误 username=%s", req.username)
        _generic_auth_error()
    # 登录成功 → 清零失败计数
    if attempts or last_failed:
        _clear_failed_login(uid)
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
    # 2026-07-31 P0-1 修复: cookie 模式
    access, refresh, ajti, rjti = _issue_train_token_pair(uid, request)
    _record_token(uid, ajti, rjti)
    set_train_cookies(response, access, refresh)
    return {
        "access_token": access,  # 兼容旧调用
        "token": access,
        "user_id": uid,
        "username": username,
        "display_name": display_name or username,
        "user": {"id": uid, "username": username, "nickname": display_name or username},
    }


@router.post("/logout")
def logout(response: Response, user: dict = Depends(get_current_train_user)):
    """登出:吊销该用户所有 train_token + 清 cookie"""
    _revoke_all_for(user["id"])
    clear_train_cookies(response)
    return {"message": "已登出"}


@router.post("/refresh")
def refresh(request: Request, response: Response):
    """用 refresh token 换新 access + 旋转 refresh (P0-2 修复)。"""
    rt = request.cookies.get(TRAIN_REFRESH_COOKIE)
    # 兼容旧 Bearer 调用
    if not rt:
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            rt = auth.split(" ", 1)[1].strip()
    if not rt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 refresh token",
        )
    try:
        payload = decode_token(rt, expected_type="refresh")
    except HTTPException:
        raise
    kind = payload.get("kind")
    sub = payload.get("sub")
    if kind != "train" or not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh token 类型错误",
        )
    rjti = payload.get("jti", "")
    if not rjti or is_refresh_revoked(rjti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh token 已失效",
        )
    # 解析 sub 到 user_id
    try:
        uid = int(sub)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh token sub 非法",
        )
    # 吊销旧 refresh, 记录新 access + refresh
    _revoke_refresh(rjti)
    new_access, new_refresh, new_ajti, new_rjti = _issue_train_token_pair(uid, request)
    _record_token(uid, new_ajti, new_rjti)
    set_train_cookies(response, new_access, new_refresh)
    return {
        "access_token": new_access,  # 兼容旧调用
        "user_id": uid,
    }


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
def change_password(
    req: ChangePwReq,
    response: Response,
    user: dict = Depends(get_current_train_user),
):
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
    # 改密 → 吊销所有 token + 清 cookie (2026-07-31 P0-1 修复)
    _revoke_all_for(user["id"])
    clear_train_cookies(response)
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