from pathlib import Path

from tools.base_tool import ToolContext
from tools.collect import tiktok_video


def test_tiktok_video_rejects_non_tiktok_url(tmp_path: Path) -> None:
    result = tiktok_video.execute(
        {"url": "https://example.com/video/1", "material_dir": str(tmp_path)},
        ToolContext(mock=True),
    )
    assert result.ok is False
    assert result.error["category"] == "validation"


def test_tiktok_video_mock_preserves_operator_transcript(tmp_path: Path) -> None:
    result = tiktok_video.execute(
        {
            "url": "https://www.tiktok.com/@demo/video/123",
            "material_dir": str(tmp_path),
            "transcript_text": "A controlled transcript",
        },
        ToolContext(mock=True),
    )
    assert result.ok is True
    assert result.data["transcript_source"] == "operator"
    assert result.data["transcript_text"] == "A controlled transcript"
