"""
登录与鉴权 API - 管理端

P0 加固:
- 登录限速
- 错误文案统一(防账号枚举)
- 失败计数 + 账号锁定
- access + refresh 双 token
- 同时下发 httpOnly cookie(access/refresh) + 可读 CSRF cookie
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    create_csrf_token,
    decode_token,
    fingerprint_for,
    is_refresh_revoked,
    issue_token_pair,
    rotate_refresh,
    set_auth_cookies,
    clear_auth_cookies,
    refresh_jti_from_payload,
    revoke_refresh,
    revoke_all_refresh_for,
)
from app.config import settings
from app.database import (
    get_user_by_username,
    is_user_locked,
    record_failed_login,
    update_last_login,
)
from app.deps import get_current_user
from app.models import LoginRequest, Resp, UserInfo
from app.rate_limit import limiter


log = logging.getLogger("app.auth")

router = APIRouter(prefix="/api/auth", tags=["登录"])

# 锁定阈值
LOCK_MAX_ATTEMPTS = 5
LOCK_WINDOW_MINUTES = 15


def _generic_login_error():
    """统一登录失败文案,防账号枚举。"""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="账号或密码错误",
    )


@router.post("/login", response_model=Resp)
@limiter.limit(settings.LOGIN_RATE_LIMIT)
def login(payload: LoginRequest, request: Request, response: Response):
    """JSON 登录(供前端 fetch)"""
    username = (payload.username or "").strip()
    password = payload.password or ""
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入账号和密码",
        )

    user = get_user_by_username(username)
    if not user or not user.get("is_active"):
        # 用户不存在/已停用 → 同样返回"账号或密码错误"
        log.info("[LOGIN] 失败:用户不存在或已停用 username=%s", username)
        _generic_login_error()
    if is_user_locked(user, max_attempts=LOCK_MAX_ATTEMPTS,
                      window_minutes=LOCK_WINDOW_MINUTES):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试次数过多,请稍后再试",
        )
    # 真实校验
    from app.database import verify_password
    if not verify_password(password, user["password_hash"], user["salt"]):
        try:
            record_failed_login(user["id"])
        except Exception:
            pass
        log.info("[LOGIN] 失败:密码错误 username=%s", username)
        _generic_login_error()

    # 登录成功
    update_last_login(user["id"])
    access, refresh = issue_token_pair(
        subject=user["username"], user_id=user["id"], request=request,
        extra={"kind": "admin"},
    )
    csrf = create_csrf_token()
    set_auth_cookies(response, access, refresh, csrf)

    return Resp(data={
        "access_token": access,   # 兼容旧前端(Bearer 模式仍可工作)
        "token_type": "bearer",
        "username": user["username"],
        "user_id": user["id"],
        "must_change_pw": bool(user.get("must_change_pw")),
        "csrf_token": csrf,
    })


@router.post("/login/form", response_model=Resp)
@limiter.limit(settings.LOGIN_RATE_LIMIT)
def login_form(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """OAuth2 表单登录(供 Swagger Authorize)"""
    username = (form_data.username or "").strip()
    password = form_data.password or ""

    user = get_user_by_username(username)
    if not user or not user.get("is_active"):
        _generic_login_error()
    if is_user_locked(user, max_attempts=LOCK_MAX_ATTEMPTS,
                      window_minutes=LOCK_WINDOW_MINUTES):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="登录尝试次数过多,请稍后再试",
        )
    from app.database import verify_password
    if not verify_password(password, user["password_hash"], user["salt"]):
        try:
            record_failed_login(user["id"])
        except Exception:
            pass
        _generic_login_error()

    update_last_login(user["id"])
    access, refresh = issue_token_pair(
        subject=user["username"], user_id=user["id"], request=request,
        extra={"kind": "admin"},
    )
    csrf = create_csrf_token()
    set_auth_cookies(response, access, refresh, csrf)

    return Resp(data={
        "access_token": access,
        "token_type": "bearer",
        "username": user["username"],
        "user_id": user["id"],
    })


@router.post("/refresh", response_model=Resp)
def refresh(request: Request, response: Response):
    """用 refresh token 换新的 access(+ 旋转 refresh)。"""
    rt = request.cookies.get("tdj_refresh")
    if not rt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 refresh token",
        )
    try:
        payload = decode_token(rt, expected_type="refresh")
    except HTTPException:
        raise
    jti = payload.get("jti", "")
    if not jti or is_refresh_revoked(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh token 已失效",
        )
    subject = payload.get("sub")
    extra = {k: v for k, v in payload.items() if k in ("kind",)}
    access, new_refresh = issue_token_pair(
        subject=subject, request=request, extra=extra,
    )
    # 旋转 refresh
    try:
        rotate_refresh(jti, refresh_jti_from_payload(new_refresh), subject)
    except Exception as e:
        log.warning("rotate refresh 失败: %s", e)
    csrf = create_csrf_token()
    set_auth_cookies(response, access, new_refresh, csrf)
    return Resp(data={"access_token": access})


@router.get("/me", response_model=Resp)
def me(user: dict = Depends(get_current_user)):
    return Resp(data=user)


@router.post("/logout", response_model=Resp)
def logout(response: Response, user: dict = Depends(get_current_user)):
    """登出:吊销全部 refresh + 清 cookie + (可选)强制下线"""
    try:
        revoke_all_refresh_for(user["username"])
    except Exception as e:
        log.warning("revoke_all_refresh 失败: %s", e)
    clear_auth_cookies(response)
    return Resp(message="已登出")


@router.post("/change-password", response_model=Resp)
def change_password(
    payload: dict,
    request: Request,
    response: Response,
    user: dict = Depends(get_current_user),
):
    """修改当前用户密码(改完自动吊销所有 refresh)"""
    from app.database import hash_password, verify_password

    old = (payload.get("old_password") or "")
    new = (payload.get("new_password") or "")
    if not old or not new or len(new) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="参数错误,新密码长度需 ≥ 6",
        )

    full = get_user_by_username(user["username"])
    if not full or not verify_password(old, full["password_hash"], full["salt"]):
        raise HTTPException(status_code=400, detail="原密码错误")

    h, salt = hash_password(new)
    from db.database import get_conn
    with get_conn() as conn:
        conn.execute(
            "UPDATE admin_user SET password_hash=?, salt=?, must_change_pw=0 WHERE id=?",
            (h, salt, user["id"]),
        )
    # 改密 → 吊销所有 refresh
    try:
        revoke_all_refresh_for(user["username"])
    except Exception:
        pass
    clear_auth_cookies(response)
    return Resp(message="密码已修改,请重新登录")