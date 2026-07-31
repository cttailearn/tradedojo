"""
训练端的依赖项:单独的 Token 命名空间,与管理员区分开,
但复用同一个 JWT secret。

P0-1 修复 (2026-07-31): 训练端 access token 改用 httpOnly cookie 而非 Bearer header。
  - 优先从 cookie 读 `tdj_train_access` (httpOnly + SameSite=Lax + Secure(prod))
  - 回退到 Authorization Bearer header (兼容旧调用,会在 access 过期后自然淘汰)
  - access token 绑定客户端指纹 (UA + Accept-Language + Accept-Encoding) 防止 token 泄露后被滥用

P0-2 修复 (2026-07-31): 训练端 refresh 机制
  - refresh token 走 `/api/train/refresh` 旋转 + DB 吊销
  - train_token 表加 revoked/refresh_jti 列
"""
import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.auth import (
    TRAIN_ACCESS_COOKIE,
    TRAIN_REFRESH_COOKIE,
    create_access_token,
    decode_token,
    fingerprint_for,
)
from app.config import settings
from db.database import user_query_one


oauth2_scheme_train = OAuth2PasswordBearer(tokenUrl="/api/train/login", auto_error=False)


def hash_train_pw(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """训练用户密码 hash (pbkdf2_sha256)。供 train_admin 复用。"""
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000
    )
    return h.hex(), salt


# 兼容旧名,旧引用 _hash_pw
_hash_pw = hash_train_pw


def _extract_train_token(request: Request) -> Optional[str]:
    """优先读训练端 cookie, 回退到 Authorization Bearer (兼容旧调用)。"""
    cookie = request.cookies.get(TRAIN_ACCESS_COOKIE)
    if cookie:
        return cookie
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


def get_current_train_user(
    request: Request,
    bearer_token: Optional[str] = Depends(oauth2_scheme_train),
) -> dict:
    """训练端用户鉴权 (P0-1 修复后, 优先 cookie, 绑定指纹)。"""
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证身份",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = _extract_train_token(request) or bearer_token
    if not token:
        raise cred_exc

    try:
        # 绑定指纹(若有 fp claim): UA + Accept-Language + Accept-Encoding
        fp = fingerprint_for(request)
        payload = decode_token(token, expected_type="access", fingerprint=fp)
        kind = payload.get("kind")
        sub = payload.get("sub")
        if kind != "train" or not sub:
            raise cred_exc
        if str(sub).isdigit():
            row = user_query_one(
                "SELECT id, username, display_name, last_login, is_active "
                "FROM training_user WHERE id = ?",
                (int(sub),),
            )
        else:
            username = str(sub)
            row = user_query_one(
                "SELECT id, username, display_name, last_login, is_active "
                "FROM training_user WHERE username = ?",
                (username,),
            )
    except HTTPException:
        raise
    except JWTError:
        raise cred_exc

    if not row:
        raise cred_exc
    if not row[4]:
        raise cred_exc
    return {
        "id": row[0],
        "username": row[1],
        "display_name": row[2],
        "last_login": row[3],
    }
