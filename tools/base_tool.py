from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    cost_cny: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None
