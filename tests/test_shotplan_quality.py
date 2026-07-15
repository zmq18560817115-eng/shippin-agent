from tools.base_tool import ToolContext
from tools.llm import doubao_shotplan
from tools.llm.doubao_shotplan import _normalize_shots
from tools.llm.mock_artifacts import mock_script_copy


def test_normalized_shots_lock_scene_character_product_and_action_continuity() -> None:
    script = mock_script_copy("continuity-demo")
    plan = _normalize_shots(
        [],
        script,
        scene_continuity="one stable night bedroom",
        character_continuity="same caregiver in a blue shirt",
    )

    assert len(plan) == 5
    assert all("one stable night bedroom" in shot["seedance_prompt"] for shot in plan)
    assert all("same caregiver in a blue shirt" in shot["seedance_prompt"] for shot in plan)
    assert all("approved white-background hero reference" in shot["seedance_prompt"] for shot in plan)
    assert all("98 degrees Fahrenheit" in shot["seedance_prompt"] for shot in plan)
    assert "pour from an approved source into the cup" in plan[2]["seedance_prompt"]
    assert "pour through its round spout" in plan[3]["seedance_prompt"]


def test_real_shotplan_reads_product_facts_and_returns_five_shots(monkeypatch) -> None:
    captured = {}

    def fake_chat_json(context, **kwargs):
        captured["messages"] = kwargs["messages"]
        return {"shots": []}, {"provider": "ark", "model": "test"}

    monkeypatch.setattr(doubao_shotplan.ark, "chat_json", fake_chat_json)
    monkeypatch.setattr(
        doubao_shotplan.product_library,
        "product_guardrail_text",
        lambda product_id: "Approved product facts: separate cup and bottle.",
    )
    result = doubao_shotplan.execute(
        {"project_id": "real-shotplan", "script_copy": mock_script_copy("real-shotplan")},
        ToolContext.from_mapping({"mock": False, "env": {"DOUBAO_API_KEY": "configured"}}),
    )

    assert result.ok is True
    assert len(result.data["shot_plan"]["shots"]) == 5
    assert "Approved product facts" in captured["messages"][1]["content"]
