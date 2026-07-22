from tools.base_tool import ToolContext
from tools.llm import doubao_analyze


def test_real_analysis_stays_grounded_in_reference_transcript(monkeypatch) -> None:
    captured = {}

    def fake_chat_json(context, **kwargs):
        captured.update(kwargs)
        return (
            {
                "hook_3s": "夜间喂养时拿出便携恒温杯",
                "structure": ["钩子", "步骤", "结果"],
                "voiceover_text": "恒温杯广告文案",
                "pacing": [],
                "keyframes": [],
                "shot_breakdown": [
                    {
                        "number": index + 1,
                        "timing": f"{index * 6}-{(index + 1) * 6}s",
                        "visual": "恒温杯与奶瓶",
                        "action": "显示 98°F",
                        "purpose": "产品证明",
                        "transition": "切换",
                    }
                    for index in range(5)
                ],
                "fingerprint": "test",
            },
            {"response_id": "test"},
        )

    monkeypatch.setattr(doubao_analyze.ark, "chat_json", fake_chat_json)
    transcript = "First cross the wide end over the narrow end. Pull it through the loop. Tighten the knot."

    result = doubao_analyze.execute(
        {"transcript_text": transcript, "duration_seconds": 46},
        ToolContext(mock=False, env={"DOUBAO_API_KEY": "test"}),
    )

    assert result.ok is True
    report = result.data["analysis_report"]
    assert report["voiceover_text"] == transcript
    assert "恒温杯" not in report["hook_3s"]
    assert "恒温杯" not in str(report["shot_breakdown"])
    assert transcript[:30] in captured["messages"][1]["content"]
    assert "不得主动加入恒温杯" in captured["messages"][1]["content"]
