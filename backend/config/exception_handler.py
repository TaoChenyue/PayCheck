"""统一异常处理 — 404/400/500 返回友好 JSON 响应。

所有未捕获异常在此转换为一致的 JSON 格式，
前端可以依赖统一的 error structure 展示错误信息。
"""

import logging
from django.http import Http404, JsonResponse
from django.core.exceptions import PermissionDenied, ValidationError
from rest_framework.exceptions import (
    APIException,
    NotAuthenticated,
    NotFound,
    MethodNotAllowed,
    ParseError,
)
from rest_framework.views import set_rollback

logger = logging.getLogger("paycheck.exception")


def custom_exception_handler(exc, context):
    """DRF 自定义异常处理器。

    将所有异常转换为统一 JSON 格式：
    {
        "error": true,
        "code": "not_found" | "validation_error" | "server_error" | ...,
        "message": "人类可读的错误描述",
        "detail": { ... 详细错误信息（可选） }
    }
    """
    # Let DRF handle its own exceptions first
    from rest_framework.views import exception_handler as drf_handler
    response = drf_handler(exc, context)

    if response is not None:
        # DRF recognized the exception — normalize the format
        status_code = response.status_code
        data = _build_error_response(exc, status_code, response.data)
        return JsonResponse(data, status=status_code)

    # Non-DRF exceptions — convert to DRF-style
    set_rollback()

    if isinstance(exc, Http404):
        return JsonResponse(
            _build_error_response(exc, 404, {"detail": str(exc)}),
            status=404,
        )
    elif isinstance(exc, PermissionDenied):
        return JsonResponse(
            _build_error_response(exc, 403, {"detail": str(exc)}),
            status=403,
        )
    elif isinstance(exc, ValidationError):
        return JsonResponse(
            _build_error_response(exc, 400, {"detail": str(exc)}),
            status=400,
        )

    # Unhandled server error — log and return 500
    logger.exception("Unhandled exception in %s: %s", context.get("view"), exc)
    return JsonResponse(
        {
            "error": True,
            "code": "server_error",
            "message": "服务器内部错误，请稍后重试",
            "detail": str(exc) if __debug__ else None,
        },
        status=500,
    )


def _build_error_response(exc, status_code, detail=None):
    """Build normalized error response dict."""
    code_map = {
        400: "validation_error",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        429: "rate_limited",
        500: "server_error",
    }

    message_map = {
        400: "请求参数有误",
        401: "未授权访问",
        403: "没有访问权限",
        404: "请求的资源不存在",
        405: "不支持的请求方法",
        429: "请求过于频繁，请稍后重试",
        500: "服务器内部错误",
    }

    code = code_map.get(status_code, "unknown_error")
    message = message_map.get(status_code, str(exc) if detail else "未知错误")

    result = {
        "error": True,
        "code": code,
        "message": message,
    }

    # Include detail for validation errors
    if detail:
        if isinstance(detail, dict):
            result["detail"] = detail
        elif isinstance(detail, list):
            result["detail"] = detail
        else:
            result["detail"] = str(detail)

    return result
