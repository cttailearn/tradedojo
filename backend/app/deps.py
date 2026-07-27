"""
FastAPI 依赖项 - 管理端鉴权

P0 加固:
- 优先读 cookie(双 token 模式),回退到 Bearer header
- access token 绑定 UA 指纹,不一致即拒绝
- must_change_pw 用户强制改密
"""
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.auth import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    CSRF_HEADER,
    decode_token,
    fingerprint_for,
)
from app.config import settings
from app.database import get_user_by_username


log = logging.getLogger("app.auth")

# auto_error=False: 手动从 cookie / header 取
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def _extract_token(request: Request) -> Optional[str]:
    """优先 cookie,再 Authorization header。"""
    token = request.cookies.get(ACCESS_COOKIE)
    if token:
        return token
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return None


def _verify_csrf_if_cookie(request: Request) -> None:
    """
    写操作时若 token 来自 cookie,必须校验 CSRF(双 cookie 模式)。
    GET / OPTIONS / HEAD 跳过。
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    token_via_cookie = bool(request.cookies.get(ACCESS_COOKIE))
    if not token_via_cookie:
        return
    cookie_csrf = request.cookies.get(CSRF_COOKIE)
    header_csrf = request.headers.get(CSRF_HEADER)
    if not cookie_csrf or not header_csrf or cookie_csrf != header_csrf:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF 校验失败",
        )


def get_current_user(
    request: Request,
    bearer_token: Optional[str] = Depends(oauth2_scheme),
) -> dict:
    """解析当前登录用户。"""
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证身份",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = _extract_token(request) or bearer_token
    if not token:
        raise cred_exc
    try:
        fp = fingerprint_for(request)
        payload = decode_token(token, expected_type="access", fingerprint=fp)
        username: str = payload.get("sub")
        if not username:
            raise cred_exc
    except HTTPException:
        raise
    except Exception:
        raise cred_exc

    user = get_user_by_username(username)
    if not user or not user.get("is_active"):
        raise cred_exc

    _verify_csrf_if_cookie(request)

    return {
        "id": user["id"],
        "username": user["username"],
        "last_login": user.get("last_login"),
        "must_change_pw": bool(user.get("must_change_pw")),
    }


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """要求登录(所有管理接口都加这个依赖)"""
    return user


# 保留给 Swagger / 测试
def decode_raw(token: str) -> dict:
    """无指纹校验的解码(用于内部场景,慎用)。"""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])