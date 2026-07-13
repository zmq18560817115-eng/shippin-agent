from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


Handler = Callable[[Mapping[str, Any]], dict[str, Any] | None]
HANDLERS: dict[str, Handler] = {}


class TaskExecutionError(Exception):
    category = "fatal"
    retryable = False
    terminal_status = "failed"


class TransientTaskError(TaskExecutionError):
    category = "transient"
    retryable = True
    terminal_status = "failed"


class ValidationTaskError(TaskExecutionError):
    category = "validation"
    retryable = True
    terminal_status = "failed"


class BlockedTaskError(TaskExecutionError):
    category = "blocked"
    retryable = False
    terminal_status = "blocked"


class FatalTaskError(TaskExecutionError):
    category = "fatal"
    retryable = False
    terminal_status = "failed"


@dataclass(frozen=True)
class TaskRunResult:
    status: str
    result: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    retryable: bool = False


def register_handler(agent: str, handler: Handler | None = None):
    def decorator(func: Handler) -> Handler:
        HANDLERS[agent] = func
        return func

    if handler is not None:
        return decorator(handler)
    return decorator


def run_task(task: Mapping[str, Any]) -> TaskRunResult:
    try:
        result = _run_dummy_task(task) if _dummy_tasks_enabled(task) else _run_registered(task)
        return TaskRunResult(status="succeeded", result=result or {})
    except TaskExecutionError as exc:
        return TaskRunResult(
            status=exc.terminal_status,
            error=_error_payload(exc),
            retryable=exc.retryable,
        )
    except Exception as exc:  # pragma: no cover - deliberately defensive worker boundary
        wrapped = FatalTaskError(str(exc))
        return TaskRunResult(status="failed", error=_error_payload(wrapped), retryable=False)


def _run_registered(task: Mapping[str, Any]) -> dict[str, Any] | None:
    agent = str(task["agent"])
    handler = HANDLERS.get(agent)
    if handler is None:
        raise BlockedTaskError(f"handler not implemented for agent: {agent}")
    return handler(task)


def _dummy_tasks_enabled(task: Mapping[str, Any]) -> bool:
    return (
        os.environ.get("VAF_ENABLE_DUMMY_TASKS") == "1"
        and task.get("task_type") == "dummy"
    )


def _run_dummy_task(task: Mapping[str, Any]) -> dict[str, Any]:
    payload = task.get("payload_json") or {}
    mode = payload.get("dummy", "success")
    attempt = int(task.get("attempt", 0))

    if mode == "success":
        return {"dummy": "ok", "attempt": attempt}
    if mode == "sleep_then_success":
        success_after_attempt = int(payload.get("success_after_attempt", 2))
        if attempt >= success_after_attempt:
            return {"dummy": "ok", "attempt": attempt}
        time.sleep(float(payload.get("sleep_s", 30)))
        return {"dummy": "slept", "attempt": attempt}
    if mode == "sleep":
        time.sleep(float(payload.get("sleep_s", 1)))
        return {"dummy": "slept", "attempt": attempt}
    if mode == "fail_retryable":
        raise TransientTaskError("dummy retryable failure")
    if mode == "fail_validation":
        raise ValidationTaskError("dummy validation failure")
    if mode == "blocked":
        raise BlockedTaskError("dummy blocked")
    raise FatalTaskError(f"unknown dummy mode: {mode}")


def _error_payload(exc: TaskExecutionError) -> dict[str, Any]:
    return {
        "category": exc.category,
        "message": str(exc),
        "exception": exc.__class__.__name__,
        "retryable": exc.retryable,
    }
