from pathlib import Path

from libshared.creative_quality import assess_script, assess_storyboard
from orchestrator import engine, queue
from tools.llm.mock_artifacts import mock_script_copy, mock_shot_plan


def test_mock_creative_artifacts_pass_quality_gate() -> None:
    script = mock_script_copy("quality-pass")
    plan = mock_shot_plan("quality-pass", script)

    assert assess_script(script)["status"] == "PASS"
    assert assess_storyboard(plan, script)["status"] == "PASS"


def test_script_assessment_explains_missing_story_and_actions() -> None:
    script = mock_script_copy("quality-script-fail")
    for section in script["sections"]:
        section["action_zh"] = ""
        section["story_beat_zh"] = "重复剧情"

    report = assess_script(script)

    assert report["status"] == "NEEDS_REWRITE"
    assert report["score"] < 80
    assert "每段都必须包含旁白、场景、动作和剧情推进" in report["issues"]
    assert "五段剧情推进不能重复" in report["rewrite_instruction"]


def test_storyboard_assessment_rejects_repeated_static_shots() -> None:
    script = mock_script_copy("quality-board-fail")
    plan = mock_shot_plan("quality-board-fail", script)
    for shot in plan["shots"]:
        shot["visual"] = "同一个白底产品静止画面"
        shot["camera_motion"]["type"] = "static"

    report = assess_storyboard(plan, script)

    assert report["status"] == "NEEDS_REWRITE"
    assert "镜头画面不能重复" in report["issues"]
    assert "至少使用两种景别或镜头运动" in report["issues"]


def test_engine_queues_only_one_targeted_creative_rewrite(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    run_root = tmp_path / "runs" / "quality-retry"
    queue.init_db(db_path)
    queue.ensure_project("quality-retry", db_path=db_path)
    task_id = queue.enqueue_task(
        project_id="quality-retry",
        stage="script",
        agent="script",
        payload={"run_root": run_root.as_posix()},
        db_path=db_path,
    )
    task = queue.claim_task("engine", agents=["script"], db_path=db_path)
    assert task is not None and task.id == task_id
    script = mock_script_copy("quality-retry")
    for section in script["sections"]:
        section["story_beat_zh"] = "重复剧情"
    script["quality_assessment"] = assess_script(script)

    queued = engine._queue_creative_rewrite_once(
        task,
        run_root,
        artifact_name="script_copy",
        payload=script,
        script_copy=None,
        db_path=db_path,
    )

    assert queued is True
    rewrite = [item for item in queue.list_tasks(project_id="quality-retry", db_path=db_path) if item.id != task_id]
    assert len(rewrite) == 1
    assert rewrite[0].payload_json["quality_retry"] is True
    assert "五段剧情推进不能重复" in rewrite[0].payload_json["rewrite_reason"]
