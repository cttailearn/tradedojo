"""
安全响应头中间件

P1 加固:
- Strict-Transport-Security (生产)
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: 最小化浏览器能力
- Content-Security-Policy: 基础 CSP(管理后台 + 后端 API)
"""
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings


log = logging.getLogger("app.security")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        # HSTS: 仅当后端直连 HTTPS 时才有意义;反代场景由 nginx 设置
        if not settings.is_dev:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={settings.HSTS_MAX_AGE}; includeSubDomains",
            )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=()",
        )
        # CSP: 管理后台/纯 API 不需要执行第三方 JS,基础策略足够
        # API 响应是 JSON,CSP 影响有限;SPA 静态页面由前端 index.html 单独配置更精确
        csp = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'self';"
        )
        # API 文档(Swagger)需要 inline script+style,这里放行
        if request.url.path.startswith(("/docs", "/redoc", "/openapi")):
            csp = (
                "default-src 'self'; "
                "img-src 'self' data: https:; "
                "style-src 'self' 'unsafe-inline' https:; "
                "script-src 'self' 'unsafe-inline' https:; "
                "object-src 'none'; "
                "frame-ancestors 'none';"
            )
        response.headers.setdefault("Content-Security-Policy", csp)
        return response