from tools import tool_registry
from tools.base_tool import ToolResult


def test_tool_result_helpers() -> None:
    ok = ToolResult.success({"value": 1}, cost_cny=0.1, meta={"mock": True})
    failed = ToolResult.failure("not_configured", "missing key")

    assert ok.ok
    assert ok.data == {"value": 1}
    assert ok.cost_cny == 0.1
    assert ok.meta == {"mock": True}
    assert not failed.ok
    assert failed.error == {"category": "not_configured", "message": "missing key"}


def test_unknown_tool_returns_tool_error() -> None:
    result = tool_registry.execute_tool("does_not_exist", {}, context={"mock": True})

    assert not result.ok
    assert result.error["category"] == "tool_error"
