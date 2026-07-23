from pathlib import Path

from tools.video import visual_qa


def test_visual_qa_blocks_forbidden_celsius(monkeypatch, tmp_path: Path) -> None:
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"fake")
    monkeypatch.setattr(visual_qa.shutil, "which", lambda name: "tesseract")
    monkeypatch.setattr(visual_qa, "_ocr_frame", lambda path, executable: "98 C")
    report = visual_qa.inspect_review_frames([frame.as_posix()], product_id="便携恒温杯")
    assert report["status"] == "BLOCKED"
    assert report["checks"]["no_forbidden_celsius"] is False


def test_visual_qa_accepts_fahrenheit_but_keeps_human_review(monkeypatch, tmp_path: Path) -> None:
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"fake")
    monkeypatch.setattr(visual_qa.shutil, "which", lambda name: "tesseract")
    monkeypatch.setattr(visual_qa, "_ocr_frame", lambda path, executable: "98°F")
    report = visual_qa.inspect_review_frames([frame.as_posix()], product_id="便携恒温杯")
    assert report["status"] == "PASS"
    assert report["checks"]["valid_98f_detected"] is True
    assert "人工确认" in report["summary"]


def test_visual_qa_reports_truthful_degraded_state_without_ocr(monkeypatch, tmp_path: Path) -> None:
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"fake")
    monkeypatch.setattr(visual_qa.shutil, "which", lambda name: None)
    report = visual_qa.inspect_review_frames([frame.as_posix()], product_id="便携恒温杯")
    assert report["status"] == "NEEDS_REVIEW"
    assert report["engine"] == "not_configured"


def test_extract_review_frames_returns_empty_without_ffmpeg(monkeypatch, tmp_path: Path) -> None:
    video = tmp_path / "take.mp4"
    video.write_bytes(b"not-a-video")
    monkeypatch.setattr(visual_qa.shutil, "which", lambda name: None)
    assert visual_qa.extract_review_frames(video, tmp_path / "frames") == []


def test_visual_qa_uses_configured_tesseract_outside_path(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "tesseract.exe"
    executable.write_bytes(b"binary")
    monkeypatch.setenv("VAF_TESSERACT_CMD", executable.as_posix())
    monkeypatch.setattr(visual_qa.shutil, "which", lambda name: None)

    assert visual_qa.resolve_tesseract() == str(executable)
