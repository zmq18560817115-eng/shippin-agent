from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "orchestrator.yaml"


@dataclass
class ToolContext:
    mock: bool = False
    run_root: Path | None = None
    env: Mapping[str, str] = field(default_factory=lambda: os.environ)
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None = None) -> "ToolContext":
        raw = dict(value or {})
        config = raw.get("config") or load_config()
        run_root = raw.get("run_root")
        return cls(
            mock=bool(raw.get("mock", False)),
            run_root=Path(run_root) if run_root else None,
            env=raw.get("env") or os.environ,
            config=config,
        )

    def pricing_for(self, tool_name: str) -> float:
        value = (self.config.get("pricing") or {}).get(tool_name)
        if value is None or isinstance(value, dict):
            return 0.0
        return float(value)

    def token_cost_cny(self, tool_name: str, *, prompt_tokens: int, completion_tokens: int) -> float:
        value = (self.config.get("pricing") or {}).get(tool_name)
        if not isinstance(value, dict):
            return 0.0
        input_rate = float(value.get("input_cny_per_1k_tokens") or 0.0)
        output_rate = float(value.get("output_cny_per_1k_tokens") or 0.0)
        return round(
            (max(prompt_tokens, 0) / 1000.0) * input_rate
            + (max(completion_tokens, 0) / 1000.0) * output_rate,
            6,
        )


@dataclass
class ToolResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    cost_cny: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None

    @classmethod
    def success(
        cls,
        data: dict[str, Any] | None = None,
        *,
        cost_cny: float = 0.0,
        meta: dict[str, Any] | None = None,
    ) -> "ToolResult":
        return cls(ok=True, data=data or {}, cost_cny=cost_cny, meta=meta or {})

    @classmethod
    def failure(
        cls,
        category: str,
        message: str,
        *,
        meta: dict[str, Any] | None = None,
    ) -> "ToolResult":
        return cls(ok=False, error={"category": category, "message": message}, meta=meta or {})


class ToolExecutionError(Exception):
    category = "tool_error"


class ToolNotConfiguredError(ToolExecutionError):
    category = "not_configured"


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


def require_env(context: ToolContext, *names: str) -> None:
    missing = [name for name in names if not str(context.env.get(name, "")).strip()]
    if missing:
        raise ToolNotConfiguredError(f"missing environment variables: {', '.join(missing)}")


def result_from_exception(exc: Exception) -> ToolResult:
    category = getattr(exc, "category", "tool_error")
    return ToolResult.failure(category, str(exc))


def dumps_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
