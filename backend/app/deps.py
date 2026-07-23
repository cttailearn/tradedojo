"""
FastAPI 依赖项
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.config import settings
from app.database import get_user_by_username


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """从 Bearer Token 中解析当前登录用户"""
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证身份",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        username: str = payload.get("sub")
        if not username:
            raise cred_exc
    except JWTError:
        raise cred_exc

    user = get_user_by_username(username)
    if not user or not user.get("is_active"):
        raise cred_exc
    return {
        "id": user["id"],
        "username": user["username"],
        "last_login": user.get("last_login"),
    }


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """要求登录(所有管理接口都加这个依赖)"""
    return user