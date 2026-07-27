"""
全局异常处理 - 脱敏

对外: 只暴露 error_id 和简略 message
对内: traceback 写日志,便于运维定位
"""
import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


log = logging.getLogger("app.errors")


def _err_resp(message: str, status_code: int, error_id: str):
    return JSONResponse(
        status_code=status_code,
        content={"code": status_code, "message": message, "error_id": error_id},
        headers={"X-Error-Id": error_id},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException):
        # 401/403/404 等业务异常按原样透传(已是友好文案)
        # 5xx 才生成 error_id 并脱敏
        eid = uuid.uuid4().hex[:16]
        if 500 <= exc.status_code < 600:
            log.error(
                "[HTTP %s] %s %s error_id=%s detail=%s",
                exc.status_code, request.method, request.url.path,
                eid, exc.detail,
            )
            return _err_resp("服务器内部错误", exc.status_code, eid)
        # 透传业务文案
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "message": str(exc.detail), "error_id": eid},
            headers=getattr(exc, "headers", None) or {"X-Error-Id": eid},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc_handler(request: Request, exc: RequestValidationError):
        eid = uuid.uuid4().hex[:16]
        # 不把原始 errors 数组直接吐回去(可能含敏感字段),仅记日志
        log.warning(
            "[VALIDATION] %s %s error_id=%s errs=%s",
            request.method, request.url.path, eid, exc.errors(),
        )
        # 取首条错误的 msg 作为对外 message
        first = (exc.errors() or [{}])[0]
        msg = first.get("msg") if isinstance(first, dict) else None
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": 422,
                "message": msg or "请求参数校验失败",
                "error_id": eid,
            },
            headers={"X-Error-Id": eid},
        )

    @app.exception_handler(Exception)
    async def unhandled_exc_handler(request: Request, exc: Exception):
        eid = uuid.uuid4().hex[:16]
        log.exception(
            "[UNHANDLED] %s %s error_id=%s",
            request.method, request.url.path, eid,
        )
        return _err_resp("服务器内部错误", 500, eid)