"""
训练端的依赖项:单独的 Token 前缀为 't_',与管理员区分开,
但复用同一个 JWT secret。
"""
import hashlib
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.config import settings
from db.database import query_one


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


def get_current_train_user(token: str = Depends(oauth2_scheme_train)) -> dict:
    """训练端用户鉴权"""
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证身份",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise cred_exc
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        kind = payload.get("kind")
        sub = payload.get("sub")
        if kind != "train" or not sub:
            raise cred_exc
        # 兼容两种 sub 格式:数字字符串(新) / 用户名(旧)
        if str(sub).isdigit():
            row = query_one(
                "SELECT id, username, display_name, last_login, is_active "
                "FROM training_user WHERE id = ?",
                (int(sub),),
            )
        else:
            username = str(sub)
            row = query_one(
                "SELECT id, username, display_name, last_login, is_active "
                "FROM training_user WHERE username = ?",
                (username,),
            )
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
