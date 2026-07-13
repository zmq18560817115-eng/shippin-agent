from __future__ import annotations

from typing import Any

from tools.base_tool import ToolContext, load_config
from tools.llm import doubao_analyze, doubao_review, doubao_script, doubao_shotplan
from tools.providers import ark


def _fake_post_json(content: dict[str, Any], *, prompt_tokens: int, completion_tokens: int):
    import json

    def _post(url: str, *, api_key: str, body: dict[str, Any], timeout_s: float):
        return {
            "id": "resp-fake",
            "choices": [{"message": {"content": json.dumps(content)}}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    return _post


def _real_context() -> ToolContext:
    return ToolContext(mock=False, env={"DOUBAO_API_KEY": "test-key"}, config=load_config())


def test_doubao_analyze_real_cost_is_nonzero_and_matches_usage_pricing(monkeypatch) -> None:
    monkeypatch.setattr(
        ark,
        "_post_json",
        _fake_post_json({"hook_3s": "h", "structure": [], "voiceover_text": "v"}, prompt_tokens=1000, completion_tokens=500),
    )
    context = _real_context()

    result = doubao_analyze.execute({"project_id": "ref-pricing", "transcript_text": "hello"}, context)

    assert result.ok
    assert result.cost_cny > 0
    expected = round((1000 / 1000.0) * 0.0008 + (500 / 1000.0) * 0.008, 6)
    assert result.cost_cny == expected


def test_doubao_script_real_cost_is_nonzero(monkeypatch) -> None:
    monkeypatch.setattr(
        ark,
        "_post_json",
        _fake_post_json({"sections": []}, prompt_tokens=800, completion_tokens=300),
    )
    context = _real_context()

    result = doubao_script.execute(
        {"project_id": "ref-pricing", "product_id": "便携恒温杯", "analysis_report": {}}, context
    )

    assert result.ok
    assert result.cost_cny > 0


def test_doubao_shotplan_real_cost_is_nonzero(monkeypatch) -> None:
    monkeypatch.setattr(
        ark,
        "_post_json",
        _fake_post_json({"shots": []}, prompt_tokens=900, completion_tokens=400),
    )
    context = _real_context()
    from tools.llm.mock_artifacts import mock_script_copy

    result = doubao_shotplan.execute(
        {"project_id": "ref-pricing", "script_copy": mock_script_copy("ref-pricing")}, context
    )

    assert result.ok
    assert result.cost_cny > 0


def test_doubao_review_real_cost_is_nonzero(monkeypatch) -> None:
    monkeypatch.setattr(
        ark,
        "_post_json",
        _fake_post_json({"status": "PASS", "scores": {}, "comments": []}, prompt_tokens=1200, completion_tokens=200),
    )
    context = _real_context()

    result = doubao_review.execute({"project_id": "ref-pricing", "script_copy": {}}, context)

    assert result.ok
    assert result.cost_cny > 0


def test_seedance_pricing_is_nonzero_flat_rate() -> None:
    context = _real_context()
    assert context.pricing_for("seedance_shot") > 0
