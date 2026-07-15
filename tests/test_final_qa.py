from __future__ import annotations

from pathlib import Path

from orchestrator.engine import _build_final_qa_report


def _inputs(tmp_path: Path, resolution: str = "720x1280") -> tuple[dict, dict, dict]:
    output = tmp_path / "final-video.mp4"
    output.write_bytes(b"\x00\x00\x00\x18ftypmp42" + (b"\x00" * 1024))
    render = {
        "output_path": output.as_posix(),
        "ffprobe": {"duration": 30.0, "resolution": resolution, "fps": 30, "audio_streams": 1},
        "input_probes": [
            {"duration": 6.0, "resolution": "720x1280", "fps": 30, "audio_streams": 1}
            for _ in range(5)
        ],
        "review_frame_paths": ["frame-01.jpg", "frame-02.jpg", "frame-03.jpg"],
    }
    plan = {
        "shots": [
            {"number": number, "camera_motion": {"duration_sec": 6}}
            for number in range(1, 6)
        ]
    }
    shots = {"shots": [{"number": n, "status": "succeeded"} for n in range(1, 6)]}
    return render, plan, shots


def _visual_review() -> dict:
    return {
        "status": "approved",
        "checks": {
            "product_identity": True,
            "no_invented_brand": True,
            "temperature_display": True,
            "usage_flow": True,
            "person_scene_continuity": True,
        },
    }


def test_final_qa_passes_compliant_vertical_video(tmp_path: Path) -> None:
    render, plan, shots = _inputs(tmp_path)
    report = _build_final_qa_report("qa-pass", tmp_path, render, plan, shots, visual_review=_visual_review())
    assert report["status"] == "PASS"
    assert report["failed_checks"] == []


def test_final_qa_blocks_square_video(tmp_path: Path) -> None:
    render, plan, shots = _inputs(tmp_path, resolution="960x960")
    report = _build_final_qa_report("qa-block", tmp_path, render, plan, shots, visual_review=_visual_review())
    assert report["status"] == "BLOCKED"
    assert "resolution_matches_aspect" in report["failed_checks"]


def test_final_qa_accepts_existing_workspace_relative_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    output = Path("data/runs/demo/artifacts/final-video.mp4")
    output.parent.mkdir(parents=True)
    output.write_bytes(b"\x00\x00\x00\x18ftypmp42" + (b"\x00" * 1024))
    render = {
        "output_path": output.as_posix(),
        "ffprobe": {"duration": 30, "resolution": "720x1280", "fps": 30, "audio_streams": 1},
        "input_probes": [{"duration": 30, "resolution": "720x1280", "fps": 30, "audio_streams": 1}],
        "review_frame_paths": ["frame-01.jpg", "frame-02.jpg", "frame-03.jpg"],
    }
    plan = {"shots": [{"number": 1, "camera_motion": {"duration_sec": 30}}]}
    shots = {"shots": [{"number": 1, "status": "succeeded"}]}
    report = _build_final_qa_report("relative", tmp_path / "data/runs/demo", render, plan, shots, visual_review=_visual_review())
    assert report["status"] == "PASS"


def test_final_qa_blocks_square_source_clips(tmp_path: Path) -> None:
    render, plan, shots = _inputs(tmp_path)
    render["input_probes"][1]["resolution"] = "960x960"
    report = _build_final_qa_report("square-source", tmp_path, render, plan, shots, visual_review=_visual_review())
    assert report["status"] == "BLOCKED"
    assert "source_clips_vertical" in report["failed_checks"]


def test_final_qa_blocks_video_shorter_than_30_second_plan(tmp_path: Path) -> None:
    render, plan, shots = _inputs(tmp_path)
    render["ffprobe"]["duration"] = 15

    report = _build_final_qa_report("short-30", tmp_path, render, plan, shots, visual_review=_visual_review())

    assert report["status"] == "BLOCKED"
    assert "duration_matches_plan" in report["failed_checks"]


def test_final_qa_blocks_placeholder_media(tmp_path: Path) -> None:
    render, plan, shots = _inputs(tmp_path)
    Path(render["output_path"]).write_bytes(b"mock video placeholder")

    report = _build_final_qa_report("placeholder", tmp_path, render, plan, shots, visual_review=_visual_review())

    assert report["status"] == "BLOCKED"
    assert "output_file_playable" in report["failed_checks"]


def test_final_qa_requires_human_visual_review(tmp_path: Path) -> None:
    render, plan, shots = _inputs(tmp_path)
    report = _build_final_qa_report("review-required", tmp_path, render, plan, shots)
    assert report["status"] == "BLOCKED"
    assert "human_visual_review" in report["failed_checks"]
