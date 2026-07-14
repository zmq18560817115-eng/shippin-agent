from __future__ import annotations

from agents.handlers import collector
from tools.base_tool import ToolResult


def test_collector_routes_oembed_task_to_provider_tool(monkeypatch) -> None:
    called: dict[str, object] = {}

    def fake_execute(name, payload, *, context):
        called.update(name=name, payload=payload, context=context)
        return ToolResult.success({"imported_count": 1})

    monkeypatch.setattr(collector.tool_registry, "execute_tool", fake_execute)
    result = collector.handle_task(
        {
            "task_type": "tiktok_oembed",
            "payload_json": {"urls": ["https://www.tiktok.com/@demo/video/1"], "mock": False},
        }
    )
    assert result["imported_count"] == 1
    assert called["name"] == "tiktok_oembed"
    assert called["context"] == {"mock": False}
