from tools.base_tool import ToolContext
from tools.llm import doubao_shotplan
from tools.llm.doubao_shotplan import _normalize_shots, _shotplan_input
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
    assert all("temperature display fully unlit" in shot["seedance_prompt"] for shot in plan[:3])
    assert all("exactly 98 degrees Fahrenheit" in shot["seedance_prompt"] for shot in plan[3:])
    assert all("90 C" in shot["seedance_prompt"] for shot in plan[3:])
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
    assert "深夜卧室" in result.data["shot_plan"]["scene_continuity"]
    assert "同一位" in result.data["shot_plan"]["character_continuity"]
    assert result.data["shot_plan"]["generation"]["structure_fallback_applied"] is True
    assert "Approved product facts" in captured["messages"][1]["content"]


def test_real_shotplan_input_is_bounded_for_model_reliability() -> None:
    script = mock_script_copy("compact-shotplan")
    script["sections"][0].update(
        {
            "scene_zh": "S" * 500,
            "action_zh": "A" * 500,
            "story_beat_zh": "B" * 500,
        }
    )

    compact = _shotplan_input(script)

    assert len(compact) == 5
    assert len(compact[0]["scene"]) == 260
    assert len(compact[0]["action"]) == 260
    assert len(compact[0]["story"]) == 180


def test_normalization_repairs_temperature_encoding_and_shot_four_action() -> None:
    script = mock_script_copy("repair-demo")
    raw = [
        {"visual": "scene", "visual_prompt": "scene"},
        {"visual": "problem", "visual_prompt": "problem"},
        {"visual": "display reads 98掳F", "visual_prompt": "display reads 98掳F"},
        {"visual": "put the cup into a travel bag", "visual_prompt": "compact travel bag"},
        {"visual": "CTA display 98°F", "visual_prompt": "CTA display 98°F"},
    ]
    shots = _normalize_shots(raw, script)
    assert "98掳F" not in str(shots)
    assert "98°F" not in str(shots)
    assert "pour through the round spout" in shots[3]["visual"]
    assert "travel bag" not in shots[3]["seedance_prompt"]
    assert "pour through the round spout" in shots[3]["seedance_prompt"]
    assert "pour through the round spout" not in shots[2]["visual"]


def test_normalization_repairs_all_static_shots_and_generated_text_requests() -> None:
    script = mock_script_copy("camera-repair")
    raw = [
        {
            "visual": f"scene {index}",
            "visual_zh": "产品画面" if index < 5 else "产品画面并配文行动号召",
            "seedance_prompt": f"opening frame {index}",
            "seedance_prompt_zh": "保持连续画面" if index < 5 else "增加字幕和品牌口号",
            "camera_motion": {"type": "static"},
        }
        for index in range(1, 6)
    ]

    shots = _normalize_shots(raw, script)

    assert len({shot["camera_motion"]["type"] for shot in shots}) >= 3
    assert shots[4]["visual_zh"] == "回到同一夜间场景，清晰展示产品并完成行动号召。"
    assert "字幕" not in shots[4]["seedance_prompt_zh"]
