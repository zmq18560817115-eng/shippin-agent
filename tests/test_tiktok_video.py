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


def test_tiktok_video_uses_first_frame_as_cover_fallback(tmp_path: Path, monkeypatch) -> None:
    material_dir = tmp_path / "material"
    material_dir.mkdir()
    video_path = material_dir / "source.mp4"
    video_path.write_bytes(b"video")
    frame_path = material_dir / "frames" / "frame-01.jpg"
    frame_path.parent.mkdir()
    frame_path.write_bytes(b"frame")
    monkeypatch.setattr(tiktok_video.shutil, "which", lambda name: "yt-dlp")
    monkeypatch.setattr(tiktok_video.subprocess, "run", lambda *args, **kwargs: type("Done", (), {"returncode": 0, "stderr": "", "stdout": ""})())
    monkeypatch.setattr(tiktok_video, "_extract_frames", lambda *args: [frame_path])

    result = tiktok_video.execute(
        {"url": "https://www.tiktok.com/@demo/video/123", "material_dir": str(material_dir), "transcript_text": "转写"},
        tiktok_video.ToolContext(mock=False, env={}),
    )

    assert result.ok is True
    assert Path(result.data["local_cover_path"]).read_bytes() == b"frame"
