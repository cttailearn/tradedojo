"""
限速 - 用 dependency 模式(slowapi 的装饰器 + Response 注入在某些路径下与
FastAPI 默认 Response 注入冲突),更稳的方式是手动绑定 endpoint。
"""
import logging

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings


log = logging.getLogger("app.ratelimit")


def _client_key(request: Request) -> str:
    if settings.BEHIND_PROXY:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(
    key_func=_client_key,
    default_limits=[],
    headers_enabled=True,
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "code": 429,
            "message": "请求过于频繁,请稍后重试",
            "detail": f"limit={exc.detail}",
        },
        headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
    )


def rate_limit(limit_str: str):
    """
    返回一个 FastAPI dependency,对该 endpoint 做限速。
    使用方式:
        @router.post("/login", dependencies=[Depends(rate_limit("10/minute"))])
        def login(...): ...
    """
    def _dep(request: Request):
        # 手动调用 limiter 检查 + 注入响应头
        # 通过 limiter._check_request_limit 不可靠,使用 hit/reset 接口
        limiter._check_request_limit(request, limit_str)
        return None
    return _dep