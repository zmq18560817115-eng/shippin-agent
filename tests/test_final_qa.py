from __future__ import annotations

from pathlib import Path

from orchestrator.engine import _build_final_qa_report


def _inputs(tmp_path: Path, resolution: str = "1080x1920") -> tuple[dict, dict, dict]:
    output = tmp_path / "final-video.mp4"
    output.write_bytes(b"video")
    render = {
        "output_path": output.as_posix(),
        "ffprobe": {"duration": 15.0, "resolution": resolution, "fps": 30, "audio_streams": 1},
        "input_probes": [
            {"duration": 5.0, "resolution": "1080x1920", "fps": 30, "audio_streams": 1}
            for _ in range(3)
        ],
    }
    plan = {"shots": [{"number": 1}, {"number": 2}, {"number": 3}]}
    shots = {"shots": [{"number": n, "status": "succeeded"} for n in range(1, 4)]}
    return render, plan, shots


def test_final_qa_passes_compliant_vertical_video(tmp_path: Path) -> None:
    render, plan, shots = _inputs(tmp_path)
    report = _build_final_qa_report("qa-pass", tmp_path, render, plan, shots)
    assert report["status"] == "PASS"
    assert report["failed_checks"] == []


def test_final_qa_blocks_square_video(tmp_path: Path) -> None:
    render, plan, shots = _inputs(tmp_path, resolution="960x960")
    report = _build_final_qa_report("qa-block", tmp_path, render, plan, shots)
    assert report["status"] == "BLOCKED"
    assert "resolution_matches_aspect" in report["failed_checks"]


def test_final_qa_accepts_existing_workspace_relative_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    output = Path("data/runs/demo/artifacts/final-video.mp4")
    output.parent.mkdir(parents=True)
    output.write_bytes(b"video")
    render = {
        "output_path": output.as_posix(),
        "ffprobe": {"duration": 15, "resolution": "1080x1920", "fps": 30, "audio_streams": 1},
        "input_probes": [{"duration": 15, "resolution": "1080x1920", "fps": 30, "audio_streams": 1}],
    }
    plan = {"shots": [{"number": 1}]}
    shots = {"shots": [{"number": 1, "status": "succeeded"}]}
    report = _build_final_qa_report("relative", tmp_path / "data/runs/demo", render, plan, shots)
    assert report["status"] == "PASS"


def test_final_qa_blocks_square_source_clips(tmp_path: Path) -> None:
    render, plan, shots = _inputs(tmp_path)
    render["input_probes"][1]["resolution"] = "960x960"
    report = _build_final_qa_report("square-source", tmp_path, render, plan, shots)
    assert report["status"] == "BLOCKED"
    assert "source_clips_vertical" in report["failed_checks"]
