import sentry_sdk
from django.conf import settings
from django.http import JsonResponse, Http404
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
    ValidationError,
    APIException,
)
from rest_framework.views import exception_handler, set_rollback

import logging

from exception import CustomException

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):  # pylint: disable=too-many-branches
    """ "
    自定义异常返回结果
    DRF内置的异常捕获handler可以处理绝大多数Exception，
    但是无法处理数据库查询等其他错误，此类其他错误都会返回None,
    此时会根据settings.DEBUG来展示对应的500页面
    """
    response = exception_handler(exc, context)
    request_data = context["request"].data

    if response is not None:
        response.data = {
            "errors": [
                {"details": ExceptionHandler.handle(exc), "object": request_data},
            ],
        }
        logger.warning("error response detail:\n%s", response.data)
        return response

    # 未捕获到的其他异常均当做500来处理，尝试包装request_id告知用户
    if settings.ENV_FLAG in ("local", "test"):
        return None

    sentry_sdk.capture_exception(exc)
    details = "服务器错误, 请联系管理员。"
    set_rollback()
    return JsonResponse(
        data={
            "errors": [{"details": details, "object": request_data}],
        },
        status=500,
        json_dumps_params={"ensure_ascii": False},
    )


class ExceptionHandler:
    DEPTH_MARK = "::"  # 表示层级关系的连接符
    EXCEPTION_MAP = {
        # 认证相关异常
        AuthenticationFailed: "authentication_error",
        NotAuthenticated: "authentication_error",
        PermissionDenied: "authentication_error",
        # 手动抛出来的逻辑相关异常
        CustomException: "api_error",
        ValidationError: "validation_error",
        # 通用异常
        Http404: "invalid_request_error",
    }

    @classmethod
    def handle(cls, exc) -> list:
        """
        :param exc: error class
        1.序列化器字段校验errors失败处理,
        2.Http404 error处理
        3.逻辑代码raise的error处理
        """
        if isinstance(exc, Http404):
            return cls._deal_http404_error(exc)
        if isinstance(exc, ValidationError):
            return cls._deal_validation_error(exc)
        return cls._deal_other_error(exc)

    @classmethod
    def _deal_validation_error(cls, exc: ValidationError) -> list:
        """序列化器参数校验失败errors"""
        errors = []
        fields = []
        cls.unpack_errors(exc.detail, errors, fields)
        return errors

    @classmethod
    def _deal_other_error(cls, exc: APIException) -> list:
        """逻辑代码raise的error处理"""
        return [
            {
                "type": cls._get_error_type(exc),
                "code": exc.get_codes(),
                "message": exc.detail,
            }
        ]

    @classmethod
    def _deal_http404_error(cls, exc: Http404) -> list:
        """htt404 errors处理"""
        return [
            {
                "type": cls._get_error_type(exc),
                "code": "general.parameter_unknown",
                "message": "请求的资源不存在。",
            }
        ]

    @classmethod
    def _get_error_type(cls, exc) -> str:
        for exc_class, exc_type in cls.EXCEPTION_MAP.items():
            if isinstance(exc, exc_class):
                return exc_type
        return "api_error"

    @classmethod
    def unpack_errors(cls, exc_detail: [dict, list], errors: list, fields: list):
        """
        :param exc_detail: 未经处理的error详情
        :param errors: 拼接错误结果
        :param fields: 记录嵌套序列化errors的层级结构
        "errors": [{
            "type": "validation_error",
            "code": "validation.delivery::address::city_code.required ",
            "message": "该字段是必填项。"}]
        """
        for field, error in exc_detail.items():
            if isinstance(error, dict):
                fields.append(field)
                ExceptionHandler.unpack_errors(error, errors, fields)
                fields = []
            elif isinstance(error, list):
                field_str = cls.DEPTH_MARK.join(fields)
                for each in error:
                    if field_str:
                        code = (
                            f"validation.{field_str}{cls.DEPTH_MARK}{field}.{each.code}"
                        )

                    else:
                        code = f"validation.{field}.{each.code}"
                    errors.append(
                        {
                            "type": "validation_error",
                            "code": code,
                            "message": str(each),
                        }
                    )
