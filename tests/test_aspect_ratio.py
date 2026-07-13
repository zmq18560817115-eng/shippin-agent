from __future__ import annotations

from pathlib import Path

from libshared import checkpoint
from orchestrator import engine, queue
from tools import tool_registry
from tools.base_tool import ToolContext, ToolResult
from tools.providers import ark
from tools.video import ffmpeg_compose, seedance_shot


def test_resolution_matches_aspect_catches_the_960x960_regression() -> None:
    # This is the exact defect the fix targets: a 960x960 (1:1) render was
    # previously accepted as a match for a 9:16 shot_plan.
    assert engine._resolution_matches_aspect("960x960", "9:16") is False
    assert engine._resolution_matches_aspect("1080x1920", "9:16") is True
    assert engine._resolution_matches_aspect("1920x1080", "16:9") is True
    assert engine._resolution_matches_aspect("1080x1080", "1:1") is True
    assert engine._resolution_matches_aspect("", "9:16") is False
    assert engine._resolution_matches_aspect("1080x1920", "unknown") is False


def test_duration_within_tolerance() -> None:
    assert engine._duration_within(15.4, 15.0, 1.5) is True
    assert engine._duration_within(17.0, 15.0, 1.5) is False
    assert engine._duration_within(None, 15.0, 1.5) is False


def test_ffmpeg_compose_mock_resolution_follows_aspect_ratio(tmp_path: Path) -> None:
    context = ToolContext(mock=True, run_root=tmp_path / "ref-ratio")
    shot_report = {"version": "2.0", "project_id": "ref-ratio", "shots": [
        {"number": 1, "status": "succeeded", "path": "shots/shot-001.mp4", "cost_cny": 0.0, "attempt": 1}
    ]}
    script_copy = {"version": "2.0", "project_id": "ref-ratio", "product_id": "p", "total_duration_s": 3, "sections": []}

    portrait = ffmpeg_compose.execute(
        {"project_id": "ref-ratio", "shot_report": shot_report, "script_copy": script_copy, "aspect_ratio": "9:16"},
        context,
    )
    landscape = ffmpeg_compose.execute(
        {"project_id": "ref-ratio", "shot_report": shot_report, "script_copy": script_copy, "aspect_ratio": "16:9"},
        context,
    )

    assert portrait.data["render_report"]["ffprobe"]["resolution"] == "1080x1920"
    assert landscape.data["render_report"]["ffprobe"]["resolution"] == "1920x1080"


def test_seedance_shot_forwards_aspect_ratio_to_ark_request(tmp_path: Path, monkeypatch) -> None:
    captured: dict = {}

    def fake_create_seedance_video(context, *, prompt, image_path, output_path, duration_sec=5, aspect_ratio="9:16"):
        captured["aspect_ratio"] = aspect_ratio
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake mp4")
        return {"provider": "ark", "model": "seedance", "task_id": "t1", "status": "succeeded", "video_url": "http://x/y.mp4"}

    monkeypatch.setattr(ark, "create_seedance_video", fake_create_seedance_video)

    context = ToolContext(
        mock=False,
        run_root=tmp_path / "ref-ratio-shot",
        env={"SEEDANCE_API_KEY": "test-key"},
    )
    asset_manifest = {
        "version": "2.0",
        "project_id": "ref-ratio-shot",
        "product_id": "便携恒温杯",
        "seedance_source": "data/01_素材库/产品资料/便携恒温杯/listing-0602-nw/主图/白底主图.png",
        "hero_frames": [
            {"number": 1, "path": "shots/hero_001.png", "source_refs": [], "status": "generated"}
        ],
    }
    result = seedance_shot.execute(
        {
            "project_id": "ref-ratio-shot",
            "shot": {"number": 1, "seedance_prompt": "p", "camera_motion": {"duration_sec": 5}},
            "asset_manifest": asset_manifest,
            "aspect_ratio": "16:9",
        },
        context,
    )

    assert result.ok
    assert captured["aspect_ratio"] == "16:9"
    assert result.meta["aspect_ratio"] == "16:9"


def test_ark_request_body_includes_ratio_and_resolution(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}
    source_image = tmp_path / "hero.png"
    source_image.write_bytes(b"\x89PNG\r\n\x1a\nfake-png-bytes")

    def fake_post_json(url, *, api_key, body, timeout_s):
        captured["body"] = body
        return {"id": "task-1", "status": "succeeded", "video_url": "http://x/final.mp4"}

    def fake_get_json(url, *, api_key, timeout_s):
        return {"id": "task-1", "status": "succeeded", "video_url": "http://x/final.mp4"}

    def fake_download(url, output_path, *, timeout_s):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake mp4 bytes")

    monkeypatch.setattr(ark, "_post_json", fake_post_json)
    monkeypatch.setattr(ark, "_get_json", fake_get_json)
    monkeypatch.setattr(ark, "_download", fake_download)

    context = ToolContext(mock=False, env={"SEEDANCE_API_KEY": "test-key", "SEEDANCE_POLL_INTERVAL_S": "0"})
    ark.create_seedance_video(
        context,
        prompt="product shot",
        image_path=str(source_image),
        output_path=tmp_path / "out.mp4",
        duration_sec=5,
        aspect_ratio="9:16",
    )

    assert captured["body"]["ratio"] == "9:16"
    assert captured["body"]["duration"] == 5
    assert captured["body"]["resolution"]
    assert "9:16" in captured["body"]["content"][0]["text"]


def test_final_qa_fails_task_when_render_resolution_mismatches_shot_plan(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    run_root = tmp_path / "runs" / "ref-qa-fail"
    queue.init_db(db_path=db_path)

    engine.start_pipeline("ref-qa-fail", product_id="便携恒温杯", db_path=db_path, run_root=run_root, mock=True)
    engine.run_until_blocked("ref-qa-fail", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("ref-qa-fail", "script_gate", approver="qa", db_path=db_path, run_root=run_root)
    engine.run_until_blocked("ref-qa-fail", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("ref-qa-fail", "hero_gate", approver="qa", db_path=db_path, run_root=run_root)

    # Simulate the real-world defect: SeedDance/ffmpeg produced a 960x960 render
    # even though shot_plan.aspect_ratio says 9:16. final_qa must now catch this.
    real_execute_tool = tool_registry.execute_tool

    def broken_execute_tool(name, payload=None, *, context=None):
        result = real_execute_tool(name, payload, context=context)
        if name == "ffmpeg_compose" and result.ok:
            result.data["render_report"]["ffprobe"]["resolution"] = "960x960"
        return result

    monkeypatch.setattr(engine.tool_registry, "execute_tool", broken_execute_tool)

    final_status = engine.run_until_blocked("ref-qa-fail", db_path=db_path, run_root=run_root, mock=True)

    assert final_status.stage == "final_qa"
    assert final_status.status == "failed"

    qa_report = (run_root / "artifacts" / "qa_report.json").read_text(encoding="utf-8")
    assert '"resolution_matches_aspect": false' in qa_report.lower() or '"resolution_matches_aspect": false' in qa_report
    assert not (run_root / "artifacts" / "publish_archive.json").exists()

    latest = checkpoint.read_latest("ref-qa-fail", run_root=run_root)
    assert latest["stage"] == "final_qa"
    assert latest["status"] == "failed"
