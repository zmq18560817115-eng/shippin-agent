from pathlib import Path
from types import SimpleNamespace

from tools.video import ffmpeg_compose


def test_xfade_preserves_requested_delivery_duration(tmp_path: Path, monkeypatch) -> None:
    clips = [tmp_path / "one.mp4", tmp_path / "two.mp4"]
    for clip in clips:
        clip.write_bytes(b"video")
    output = tmp_path / "final.mp4"
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr(ffmpeg_compose, "_probe_media", lambda *_: {"duration": 6.0})

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        captured["command"] = command
        output.write_bytes(b"composed")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(ffmpeg_compose.subprocess, "run", fake_run)

    assert ffmpeg_compose._compose_with_xfade(
        clips,
        output,
        "ffmpeg",
        0.4,
        target_duration=12.0,
    )
    command = captured["command"]
    assert command[command.index("-t") + 1] == "12.000"
    filter_complex = command[command.index("-filter_complex") + 1]
    assert "tpad=stop_mode=clone:stop_duration=0.400" in filter_complex
    assert "apad=pad_dur=0.400" in filter_complex
