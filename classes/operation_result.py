"""
Structured results shared by core and feature operations.
"""

from __future__ import annotations

from dataclasses import dataclass
import traceback
from typing import Any


@dataclass(frozen=True)
class OperationResult:
    ok: bool
    code: str = ""
    title: str = ""
    message: str = ""
    detail: str = ""
    retryable: bool = False
    data: Any = None

    def __bool__(self) -> bool:
        return self.ok

    @classmethod
    def success(cls, message: str = "", data=None):
        return cls(True, message=message, data=data)

    @classmethod
    def failure(
        cls,
        code: str,
        title: str,
        message: str,
        detail: str = "",
        retryable: bool = False,
    ):
        return cls(
            False,
            code=code,
            title=title,
            message=message,
            detail=detail,
            retryable=retryable,
        )


def ensure_result(
    value,
    failure_code: str = "UNEXPECTED_ERROR",
    failure_title: str = "Operation Failed",
    failure_message: str = "The operation could not be completed.",
) -> OperationResult:
    if isinstance(value, OperationResult):
        return value
    if value:
        return OperationResult.success()
    return OperationResult.failure(
        failure_code,
        failure_title,
        failure_message,
    )


def unexpected_result(context: str, exception) -> OperationResult:
    technical_detail = "".join(
        traceback.format_exception(
            type(exception),
            exception,
            exception.__traceback__,
        )
    ).strip()
    return OperationResult.failure(
        "UNEXPECTED_ERROR",
        "Unexpected Error",
        "An unexpected error occurred. Check the Console tab or session log for details.",
        detail=f"{context}\n\n{technical_detail}",
    )