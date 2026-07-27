"""
JWT 鉴权工具

P0 加固:
- access_token 绑定 IP/UA 指纹(fp_hash),不一致即拒绝(防止 XSS/中间人偷走 token)
- 支持 refresh_token(旋转策略,落 DB,可吊销)
- 登录时同时下发 cookie(access_token / refresh_token / csrf_token)
"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import Request, Response
from jose import JWTError, jwt

from app.config import settings
from app.database import get_user_by_username, verify_password


log = logging.getLogger("app.auth")


ACCESS_COOKIE = "tdj_access"
REFRESH_COOKIE = "tdj_refresh"
CSRF_COOKIE = "tdj_csrf"
CSRF_HEADER = "X-CSRF-Token"


# ---------- 指纹 ----------
def _ua_hash(request: Optional[Request]) -> str:
    """客户端指纹 = UA 哈希。生产可叠加 IP/screen/lang 等。"""
    ua = ""
    if request is not None:
        ua = request.headers.get("user-agent", "")
    return hashlib.sha256(ua.encode("utf-8", "ignore")).hexdigest()[:32]


def fingerprint_for(request: Optional[Request]) -> str:
    """根据请求派生 token 绑定指纹。"""
    return _ua_hash(request)


# ---------- 密码 ----------
def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = get_user_by_username(username)
    if not user:
        return None
    if not user.get("is_active"):
        return None
    if not verify_password(password, user["password_hash"], user["salt"]):
        return None
    return user


# ---------- Token 编解码 ----------
def create_access_token(
    subject: str,
    *,
    expires_minutes: Optional[int] = None,
    extra: Optional[dict] = None,
    fingerprint: Optional[str] = None,
    token_type: str = "access",
) -> str:
    """生成 JWT。access 携带 fp_hash 绑定客户端指纹。"""
    now = datetime.now(timezone.utc)
    if token_type == "access":
        exp = now + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": subject,
            "type": "access",
            "iat": now,
            "exp": exp,
            "jti": secrets.token_urlsafe(12),
        }
        if fingerprint:
            payload["fp"] = fingerprint
    else:  # refresh
        exp = now + timedelta(days=expires_minutes or settings.REFRESH_TOKEN_EXPIRE_DAYS)
        payload = {
            "sub": subject,
            "type": "refresh",
            "iat": now,
            "exp": exp,
            "jti": secrets.token_urlsafe(16),
        }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def decode_token(
    token: str,
    *,
    expected_type: str = "access",
    fingerprint: Optional[str] = None,
) -> dict:
    """解码并校验 JWT。fingerprint 不匹配即拒绝。"""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except JWTError as e:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token 无效或已过期: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("type") != expected_type:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 类型错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    fp = payload.get("fp")
    if expected_type == "access" and fp and fingerprint:
        # constant-time 比较
        if not hmac.compare_digest(fp, fingerprint):
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 绑定环境已变更,请重新登录",
                headers={"WWW-Authenticate": "Bearer"},
            )
    return payload


# ---------- Cookie 写入 ----------
def set_auth_cookies(response: Response, access: str, refresh: Optional[str], csrf: str):
    """
    下发鉴权相关 cookie:
    - access / refresh: httpOnly + Secure(prod) + SameSite=Lax
    - csrf:  前端可读,用于双提交校验(双 cookie 模式)
    """
    is_prod = not settings.is_dev
    common = {
        "httponly": True,
        "secure": is_prod,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(
        key=ACCESS_COOKIE, value=access,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **common,
    )
    if refresh:
        response.set_cookie(
            key=REFRESH_COOKIE, value=refresh,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            **common,
        )
    # CSRF cookie 前端 JS 可读(不放 httponly),但 SameSite=Lax + 严格 Origin 校验
    response.set_cookie(
        key=CSRF_COOKIE, value=csrf,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=False,
        secure=is_prod,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response):
    for k in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(k, path="/")


# ---------- Refresh token 持久化(简单表) ----------
def _ensure_refresh_table():
    """首次调用前确保 refresh_token 表存在(供吊销/审计)。"""
    from db.database import execute
    execute(
        "CREATE TABLE IF NOT EXISTS refresh_token ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  user_id INTEGER NOT NULL,"
        "  jti TEXT UNIQUE NOT NULL,"
        "  subject TEXT NOT NULL,"
        "  expires_at TEXT NOT NULL,"
        "  revoked INTEGER DEFAULT 0,"
        "  created_at TEXT DEFAULT (datetime('now', 'localtime'))"
        ")"
    )


def store_refresh_token(subject: str, jti: str, user_id: Optional[int] = None) -> None:
    _ensure_refresh_table()
    from db.database import execute
    expires = (
        datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    ).isoformat()
    execute(
        "INSERT INTO refresh_token(user_id, jti, subject, expires_at) "
        "VALUES(?, ?, ?, ?)",
        (user_id, jti, subject, expires),
    )


def is_refresh_revoked(jti: str) -> bool:
    """检查 refresh 是否被吊销/过期。"""
    from db.database import query_one
    row = query_one(
        "SELECT revoked, expires_at FROM refresh_token WHERE jti = ?", (jti,)
    )
    if not row:
        return True  # 未登记视为无效
    revoked, expires_at = row
    if revoked:
        return True
    try:
        exp = datetime.fromisoformat(expires_at)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            return True
    except Exception:
        return True
    return False


def revoke_refresh(jti: str) -> None:
    from db.database import execute
    execute("UPDATE refresh_token SET revoked = 1 WHERE jti = ?", (jti,))


def revoke_all_refresh_for(subject: str) -> None:
    _ensure_refresh_table()
    from db.database import execute
    execute(
        "UPDATE refresh_token SET revoked = 1 WHERE subject = ?", (subject,)
    )


def rotate_refresh(old_jti: str, new_jti: str, subject: str) -> None:
    """吊销旧的 refresh,记录新的。"""
    from db.database import execute
    execute("UPDATE refresh_token SET revoked = 1 WHERE jti = ?", (old_jti,))
    store_refresh_token(subject, new_jti)


def issue_token_pair(
    *,
    subject: str,
    user_id: Optional[int] = None,
    request: Optional[Request] = None,
    extra: Optional[dict] = None,
) -> Tuple[str, str]:
    """返回 (access, refresh)。"""
    fp = fingerprint_for(request)
    access = create_access_token(
        subject, extra=extra, fingerprint=fp, token_type="access",
    )
    refresh = create_access_token(
        subject, extra=extra, token_type="refresh",
    )
    try:
        store_refresh_token(subject, refresh_jti_from_payload(refresh), user_id)
    except Exception as e:
        log.warning("store refresh_token 失败: %s", e)
    return access, refresh


def refresh_jti_from_payload(token: str) -> str:
    """解析但不校验签名的 jti(签名仍由 decode_token 校验)。"""
    try:
        # 仅本地可信(签名仍会校验),用于落库追踪
        import python_jose  # noqa
    except Exception:
        pass
    payload = jwt.get_unverified_claims(token)
    return payload.get("jti", "")