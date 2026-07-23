"""
登录与鉴权 API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import authenticate_user, create_access_token, decode_token
from app.database import update_last_login, get_user_by_username
from app.deps import get_current_user
from app.models import LoginRequest, LoginResponse, UserInfo, Resp

router = APIRouter(prefix="/api/auth", tags=["登录"])


@router.post("/login", response_model=Resp)
def login(payload: LoginRequest):
    """JSON 登录(供前端 fetch)"""
    user = authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
        )
    update_last_login(user["id"])
    token = create_access_token(user["username"])
    return Resp(data={
        "access_token": token,
        "token_type": "bearer",
        "username": user["username"],
        "user_id": user["id"],
    })


@router.post("/login/form", response_model=Resp)
def login_form(form_data: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 表单登录(供 Swagger Authorize 按钮使用)"""
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    update_last_login(user["id"])
    token = create_access_token(user["username"])
    return Resp(data={
        "access_token": token,
        "token_type": "bearer",
        "username": user["username"],
        "user_id": user["id"],
    })


@router.get("/me", response_model=Resp)
def me(user: dict = Depends(get_current_user)):
    """获取当前登录用户"""
    return Resp(data=user)


@router.post("/logout", response_model=Resp)
def logout(user: dict = Depends(get_current_user)):
    """JWT 无状态,前端清掉 token 即可,这里只返回成功"""
    return Resp(message="已登出")


@router.post("/change-password", response_model=Resp)
def change_password(
    payload: dict,
    user: dict = Depends(get_current_user),
):
    """修改当前用户密码"""
    from app.database import hash_password, get_user_by_username, _orig_get_conn

    old = payload.get("old_password", "")
    new = payload.get("new_password", "")
    if not old or not new or len(new) < 6:
        raise HTTPException(status_code=400, detail="参数错误,新密码长度需 ≥ 6")

    full = get_user_by_username(user["username"])
    from app.database import verify_password
    if not verify_password(old, full["password_hash"], full["salt"]):
        raise HTTPException(status_code=400, detail="原密码错误")

    h, salt = hash_password(new)
    with _orig_get_conn() as conn:
        conn.execute(
            "UPDATE admin_user SET password_hash=?, salt=? WHERE id=?",
            (h, salt, user["id"]),
        )
    return Resp(message="密码已修改")