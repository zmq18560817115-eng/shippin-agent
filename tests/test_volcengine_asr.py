from pathlib import Path

from tools.audio import volcengine_asr
from tools.base_tool import ToolContext


def test_real_asr_requires_dedicated_credentials(tmp_path: Path) -> None:
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"audio")
    result = volcengine_asr.execute({"audio_path": audio.as_posix()}, ToolContext(mock=False, env={}))
    assert result.ok is False
    assert result.error["category"] == "not_configured"
    assert "VOLCENGINE_ASR_API_KEY" in result.error["message"]


def test_real_asr_normalizes_text_and_segments(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "clip.mp3"
    audio.write_bytes(b"audio")
    monkeypatch.setattr(
        volcengine_asr,
        "_recognize",
        lambda *args, **kwargs: {
            "result": {
                "text": "夜间准备更从容。",
                "utterances": [{"start_time": 1000, "end_time": 2600, "text": "夜间准备更从容。"}],
            }
        },
    )
    result = volcengine_asr.execute(
        {"audio_path": audio.as_posix()},
        ToolContext(mock=False, env={"VOLCENGINE_ASR_API_KEY": "secret"}),
    )
    assert result.ok is True
    assert result.data["transcript_text"] == "夜间准备更从容。"
    assert result.data["segments"] == [{"start_s": 1.0, "end_s": 2.6, "text": "夜间准备更从容。"}]
    assert result.meta["source"] == "volcengine_flash"
