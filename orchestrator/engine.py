from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from libshared import artifacts, checkpoint
from libshared.paths import ROOT, RUNS_ROOT
from orchestrator import cost_tracker, queue
from tools import tool_registry
from tools.base_tool import ToolResult
from tools.collect import product_library


WHITE_HERO_BY_PRODUCT = {
    "便携恒温杯": "data/01_素材库/产品资料/便携恒温杯/listing-0602-nw/主图/白底主图.png"
}


@dataclass(frozen=True)
class EngineRunStatus:
    project_id: str
    stage: str | None
    status: str
    message: str = ""


def start_pipeline(
    project_id: str,
    *,
    product_id: str,
    source_link_id: int | None = None,
    source_material_id: str | None = None,
    source_url: str | None = None,
    db_path: str | Path | None = None,
    run_root: str | Path | None = None,
    mock: bool = True,
) -> int:
    root = _run_root(project_id, run_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "inputs").mkdir(parents=True, exist_ok=True)
    (root / "artifacts").mkdir(parents=True, exist_ok=True)
    (root / "shots").mkdir(parents=True, exist_ok=True)
    queue.ensure_project(
        project_id,
        product_id=product_id,
        source_link_id=source_link_id,
        payload={
            "mock": mock,
            "run_root": root.as_posix(),
            "source_material_id": source_material_id,
            "source_url": source_url,
        },
        db_path=db_path,
    )
    existing = [
        task
        for task in queue.list_tasks(project_id=project_id, db_path=db_path)
        if task.stage == "analysis"
    ]
    if existing:
        return existing[0].id
    return _enqueue_stage(
        project_id,
        "analysis",
        {
            "product_id": product_id,
            "source_link_id": source_link_id,
            "source_material_id": source_material_id,
            "source_url": source_url,
            "run_root": root.as_posix(),
            "mock": mock,
        },
        db_path=db_path,
    )


def run_until_blocked(
    project_id: str,
    *,
    db_path: str | Path | None = None,
    run_root: str | Path | None = None,
    mock: bool = True,
    max_steps: int = 100,
) -> EngineRunStatus:
    root = _run_root(project_id, run_root)
    latest = checkpoint.read_latest(project_id, run_root=root)
    if latest and latest.get("status") == "awaiting_human":
        return EngineRunStatus(project_id, latest.get("stage"), "awaiting_human", "waiting for gate approval")

    for _ in range(max_steps):
        terminal = _terminal_status(project_id, root, db_path=db_path)
        if terminal:
            return terminal

        task = queue.claim_task(
            "engine",
            project_id=project_id,
            lease_seconds=60,
            db_path=db_path,
        )
        if task is None:
            latest = checkpoint.read_latest(project_id, run_root=root)
            if latest:
                return EngineRunStatus(project_id, latest.get("stage"), latest.get("status", "idle"), "no queued task")
            return EngineRunStatus(project_id, None, "idle", "no queued task")

        result = _execute_task(task, root, mock=mock, db_path=db_path)
        if result.status in {"awaiting_human", "failed", "blocked", "needs_review"}:
            return result
        if result.status == "succeeded" and result.stage == "archive":
            return result

    raise RuntimeError(f"engine exceeded max_steps={max_steps} for {project_id}")


def approve_gate(
    project_id: str,
    stage: str,
    *,
    approver: str,
    notes: str | None = None,
    db_path: str | Path | None = None,
    run_root: str | Path | None = None,
) -> EngineRunStatus:
    if stage not in {"script_gate", "hero_gate"}:
        raise ValueError(f"unknown gate stage: {stage}")
    root = _run_root(project_id, run_root)
    approved = checkpoint.approve_gate(project_id, stage, approver=approver, notes=notes, run_root=root)
    if stage == "script_gate":
        _enqueue_stage(project_id, "storyboard", {"run_root": root.as_posix()}, db_path=db_path)
    elif stage == "hero_gate":
        shot_plan = _load_artifact(root, "shot_plan")
        for shot in shot_plan["shots"]:
            _enqueue_stage(
                project_id,
                "production",
                {
                    "run_root": root.as_posix(),
                    "shot_index": int(shot["number"]),
                    "shot": shot,
                },
                db_path=db_path,
            )
    return EngineRunStatus(project_id, stage, approved["status"], "gate approved")


def retry_failed_shot(
    project_id: str,
    shot_index: int,
    *,
    db_path: str | Path | None = None,
    run_root: str | Path | None = None,
    mock: bool = True,
) -> EngineRunStatus:
    root = _run_root(project_id, run_root)
    matching = [
        task
        for task in queue.list_tasks(project_id=project_id, db_path=db_path)
        if task.stage == "production"
        and task.payload_json.get("shot_index") == shot_index
        and task.status == "failed"
    ]
    if not matching:
        raise ValueError(f"no failed production task for shot {shot_index}")
    queue.mark_task_status(matching[0].id, "queued", db_path=db_path)
    status = run_until_blocked(project_id, db_path=db_path, run_root=root, mock=mock)
    if status.stage == "production":
        return status
    latest_task = queue.get_task(matching[0].id, db_path=db_path)
    return EngineRunStatus(project_id, "production", latest_task.status, "shot retried")


def _execute_task(
    task: queue.Task,
    root: Path,
    *,
    mock: bool,
    db_path: str | Path | None,
) -> EngineRunStatus:
    try:
        if task.stage == "analysis":
            return _run_analysis(task, root, mock=mock, db_path=db_path)
        if task.stage == "script":
            return _run_script(task, root, mock=mock, db_path=db_path)
        if task.stage == "script_review":
            return _run_script_review(task, root, mock=mock, db_path=db_path)
        if task.stage == "storyboard":
            return _run_storyboard(task, root, mock=mock, db_path=db_path)
        if task.stage == "asset":
            return _run_asset(task, root, mock=mock, db_path=db_path)
        if task.stage == "production":
            return _run_production(task, root, mock=mock, db_path=db_path)
        if task.stage == "compose":
            return _run_compose(task, root, mock=mock, db_path=db_path)
        if task.stage == "final_qa":
            return _run_final_qa(task, root, db_path=db_path)
        if task.stage == "archive":
            return _run_archive(task, root, db_path=db_path)
        raise ValueError(f"unknown stage: {task.stage}")
    except Exception as exc:
        queue.fail_task(
            task.id,
            "engine",
            {"category": "engine_error", "message": str(exc)},
            retryable=False,
            db_path=db_path,
        )
        checkpoint.write_checkpoint(
            task.project_id,
            task.stage,
            status="failed",
            data={"error": str(exc)},
            run_root=root,
        )
        return EngineRunStatus(task.project_id, task.stage, "failed", str(exc))


def _run_analysis(task: queue.Task, root: Path, *, mock: bool, db_path: str | Path | None) -> EngineRunStatus:
    product_id = _project_product_id(task.project_id, db_path=db_path)
    result = _execute_tool(
        "doubao_analyze",
        {
            "project_id": task.project_id,
            "product_id": product_id,
            "source_link_id": task.payload_json.get("source_link_id"),
            "source_material_id": task.payload_json.get("source_material_id"),
            "source_url": task.payload_json.get("source_url"),
        },
        root,
        mock=mock,
    )
    return _complete_with_artifact(
        task,
        root,
        "analysis_report",
        result.data["analysis_report"],
        next_stage="script",
        db_path=db_path,
        tool="doubao_analyze",
        result=result,
    )


def _run_script(task: queue.Task, root: Path, *, mock: bool, db_path: str | Path | None) -> EngineRunStatus:
    product_id = _project_product_id(task.project_id, db_path=db_path)
    result = _execute_tool(
        "doubao_script",
        {
            "project_id": task.project_id,
            "product_id": product_id,
            "analysis_report": _load_artifact(root, "analysis_report"),
        },
        root,
        mock=mock,
    )
    return _complete_with_artifact(
        task,
        root,
        "script_copy",
        result.data["script_copy"],
        next_stage="script_review",
        db_path=db_path,
        tool="doubao_script",
        result=result,
    )


def _run_script_review(task: queue.Task, root: Path, *, mock: bool, db_path: str | Path | None) -> EngineRunStatus:
    result = _execute_tool(
        "doubao_review",
        {
            "project_id": task.project_id,
            "script_copy": _load_artifact(root, "script_copy"),
            "analysis_report": _load_artifact(root, "analysis_report"),
        },
        root,
        mock=mock,
    )
    report = result.data["review_report"]
    artifacts.save_artifact(task.project_id, "review_report", report, run_root=root)
    queue.complete_task(task.id, "engine", result.data, db_path=db_path)
    cost_tracker.reconcile(
        project_id=task.project_id,
        task_id=task.id,
        agent=task.agent,
        tool="doubao_review",
        phase="script_review",
        cost_cny=result.cost_cny,
        model=result.meta.get("model"),
        meta=result.meta,
        db_path=db_path,
    )
    checkpoint.write_checkpoint(
        task.project_id,
        "script_review",
        status="succeeded",
        artifacts={"review_report": "artifacts/review_report.json"},
        run_root=root,
    )
    if report.get("status") == "BLOCKED":
        return _requeue_script_or_needs_review(task, root, db_path=db_path)
    checkpoint.write_checkpoint(
        task.project_id,
        "script_gate",
        status="awaiting_human",
        artifacts={
            "script_copy": "artifacts/script_copy.json",
            "review_report": "artifacts/review_report.json",
        },
        run_root=root,
    )
    return EngineRunStatus(task.project_id, "script_gate", "awaiting_human", "waiting for script approval")


def _run_storyboard(task: queue.Task, root: Path, *, mock: bool, db_path: str | Path | None) -> EngineRunStatus:
    script_copy = _load_artifact(root, "script_copy")
    result = _execute_tool(
        "doubao_shotplan",
        {"project_id": task.project_id, "script_copy": script_copy},
        root,
        mock=mock,
    )
    return _complete_with_artifact(
        task,
        root,
        "shot_plan",
        result.data["shot_plan"],
        next_stage="asset",
        db_path=db_path,
        tool="doubao_shotplan",
        result=result,
        script_copy=script_copy,
    )


def _run_asset(task: queue.Task, root: Path, *, mock: bool, db_path: str | Path | None) -> EngineRunStatus:
    product_id = _project_product_id(task.project_id, db_path=db_path)
    shot_plan = _load_artifact(root, "shot_plan")
    result = _execute_tool(
        "hero_frame",
        {
            "project_id": task.project_id,
            "product_id": product_id,
            "shot_plan": shot_plan,
            "seedance_source": _seedance_source_for_product(product_id),
        },
        root,
        mock=mock,
    )
    artifacts.save_artifact(
        task.project_id,
        "asset_manifest",
        result.data["asset_manifest"],
        run_root=root,
    )
    queue.complete_task(task.id, "engine", result.data, db_path=db_path)
    checkpoint.write_checkpoint(
        task.project_id,
        "asset",
        status="succeeded",
        artifacts={"asset_manifest": "artifacts/asset_manifest.json"},
        run_root=root,
    )
    checkpoint.write_checkpoint(
        task.project_id,
        "hero_gate",
        status="awaiting_human",
        artifacts={"asset_manifest": "artifacts/asset_manifest.json"},
        run_root=root,
    )
    return EngineRunStatus(task.project_id, "hero_gate", "awaiting_human", "waiting for hero frame approval")


def _run_production(task: queue.Task, root: Path, *, mock: bool, db_path: str | Path | None) -> EngineRunStatus:
    result = _execute_tool(
        "seedance_shot",
        {
            "project_id": task.project_id,
            "shot": task.payload_json.get("shot"),
            "shot_index": task.payload_json.get("shot_index"),
            "asset_manifest": _load_artifact(root, "asset_manifest"),
            "attempt": task.attempt,
        },
        root,
        mock=mock,
        allow_failure=True,
    )
    if not result.ok:
        queue.fail_task(task.id, "engine", result.error or {}, retryable=False, db_path=db_path)
        checkpoint.write_checkpoint(
            task.project_id,
            "production",
            status="failed",
            data={"failed_shot": task.payload_json.get("shot_index"), "error": result.error},
            run_root=root,
        )
        if _has_queued_production(task.project_id, db_path=db_path):
            return EngineRunStatus(task.project_id, "production", "running", "shot failed; continuing sibling shots")
        return EngineRunStatus(task.project_id, "production", "failed", "shot generation failed")

    _merge_shot_report(root, task.project_id, result.data["shot_report"])
    queue.complete_task(task.id, "engine", result.data, db_path=db_path)
    cost_tracker.reconcile(
        project_id=task.project_id,
        task_id=task.id,
        agent=task.agent,
        tool="seedance_shot",
        phase="production",
        cost_cny=result.cost_cny,
        shot_index=task.payload_json.get("shot_index"),
        meta=result.meta,
        db_path=db_path,
    )
    if _all_production_succeeded(task.project_id, db_path=db_path):
        checkpoint.write_checkpoint(
            task.project_id,
            "production",
            status="succeeded",
            artifacts={"shot_report": "artifacts/shot_report.json"},
            run_root=root,
        )
        _enqueue_stage(task.project_id, "compose", {"run_root": root.as_posix()}, db_path=db_path)
    return EngineRunStatus(task.project_id, "production", "running", "shot completed")


def _run_compose(task: queue.Task, root: Path, *, mock: bool, db_path: str | Path | None) -> EngineRunStatus:
    result = _execute_tool(
        "ffmpeg_compose",
        {
            "project_id": task.project_id,
            "shot_report": _load_artifact(root, "shot_report"),
            "script_copy": _load_artifact(root, "script_copy"),
        },
        root,
        mock=mock,
    )
    return _complete_with_artifact(
        task,
        root,
        "render_report",
        result.data["render_report"],
        next_stage="final_qa",
        db_path=db_path,
        tool="ffmpeg_compose",
        result=result,
    )


def _run_final_qa(task: queue.Task, root: Path, *, db_path: str | Path | None) -> EngineRunStatus:
    report = {
        "version": "2.0",
        "project_id": task.project_id,
        "artifact_type": "qa_report",
        "status": "PASS",
        "qa": {
            "ffprobe_duration_within": True,
            "has_audio_stream": True,
            "resolution_matches_aspect": True,
        },
        "comments": ["Mock final QA passed."],
    }
    artifacts.save_artifact(task.project_id, "qa_report", report, run_root=root)
    queue.complete_task(task.id, "engine", {"qa_report": report}, db_path=db_path)
    checkpoint.write_checkpoint(
        task.project_id,
        "final_qa",
        status="succeeded",
        artifacts={"qa_report": "artifacts/qa_report.json"},
        run_root=root,
    )
    _enqueue_stage(task.project_id, "archive", {"run_root": root.as_posix()}, db_path=db_path)
    return EngineRunStatus(task.project_id, "final_qa", "succeeded")


def _run_archive(task: queue.Task, root: Path, *, db_path: str | Path | None) -> EngineRunStatus:
    archive = {
        "version": "2.0",
        "project_id": task.project_id,
        "artifact_type": "publish_archive",
        "status": "PASS",
        "archive": {
            "render_report_ref": "artifacts/render_report.json",
            "qa_report_ref": "artifacts/qa_report.json",
            "feedback_library": "data/05_反馈库",
        },
        "feedback_constraints": [],
        "comments": ["Mock archive completed."],
    }
    artifacts.save_artifact(task.project_id, "publish_archive", archive, run_root=root)
    queue.complete_task(task.id, "engine", {"publish_archive": archive}, db_path=db_path)
    checkpoint.write_checkpoint(
        task.project_id,
        "archive",
        status="succeeded",
        artifacts={"publish_archive": "artifacts/publish_archive.json"},
        run_root=root,
    )
    return EngineRunStatus(task.project_id, "archive", "succeeded", "pipeline complete")


def _complete_with_artifact(
    task: queue.Task,
    root: Path,
    artifact_name: str,
    payload: dict[str, Any],
    *,
    next_stage: str,
    db_path: str | Path | None,
    tool: str,
    result: ToolResult,
    script_copy: dict[str, Any] | None = None,
) -> EngineRunStatus:
    artifacts.save_artifact(task.project_id, artifact_name, payload, run_root=root, script_copy=script_copy)
    queue.complete_task(task.id, "engine", {artifact_name: payload}, db_path=db_path)
    cost_tracker.reconcile(
        project_id=task.project_id,
        task_id=task.id,
        agent=task.agent,
        tool=tool,
        phase=task.stage,
        cost_cny=result.cost_cny,
        model=result.meta.get("model"),
        meta=result.meta,
        db_path=db_path,
    )
    checkpoint.write_checkpoint(
        task.project_id,
        task.stage,
        status="succeeded",
        artifacts={artifact_name: f"artifacts/{artifact_name}.json"},
        run_root=root,
    )
    _enqueue_stage(task.project_id, next_stage, {"run_root": root.as_posix()}, db_path=db_path)
    return EngineRunStatus(task.project_id, task.stage, "succeeded", f"{artifact_name} saved")


def _execute_tool(
    name: str,
    payload: dict[str, Any],
    root: Path,
    *,
    mock: bool,
    allow_failure: bool = False,
):
    result = tool_registry.execute_tool(name, payload, context={"mock": mock, "run_root": root.as_posix()})
    if not result.ok and not allow_failure:
        raise RuntimeError(f"{name} failed: {result.error}")
    return result


def _enqueue_stage(
    project_id: str,
    stage_name: str,
    payload: dict[str, Any] | None = None,
    *,
    db_path: str | Path | None,
) -> int:
    stage = _stage_def(stage_name)
    if _stage_task_exists(project_id, stage_name, payload, db_path=db_path):
        return 0
    return queue.enqueue_task(
        project_id=project_id,
        stage=stage_name,
        agent=str(stage["agent"]),
        task_type=str(stage.get("task_type") or "default"),
        payload=payload or {},
        max_retries=int(stage.get("max_retries") or 2),
        db_path=db_path,
    )


def _stage_task_exists(
    project_id: str,
    stage_name: str,
    payload: dict[str, Any] | None,
    *,
    db_path: str | Path | None,
) -> bool:
    shot_index = (payload or {}).get("shot_index")
    for task in queue.list_tasks(project_id=project_id, db_path=db_path):
        if task.stage != stage_name:
            continue
        if shot_index is not None and task.payload_json.get("shot_index") != shot_index:
            continue
        if task.status in {"queued", "running", "succeeded", "awaiting_human"}:
            return True
    return False


def _stage_def(stage_name: str) -> dict[str, Any]:
    for stage in _pipeline_def()["stages"]:
        if stage["name"] == stage_name:
            return stage
    raise KeyError(f"stage not found: {stage_name}")


def _pipeline_def() -> dict[str, Any]:
    import yaml

    path = ROOT / "pipeline_defs" / "viral-imitate.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _project_product_id(project_id: str, *, db_path: str | Path | None) -> str:
    with queue.get_conn(db_path) as conn:
        row = conn.execute("SELECT product_id FROM projects WHERE id = ?", (project_id,)).fetchone()
    return str(row["product_id"] or "便携恒温杯")


def _seedance_source_for_product(product_id: str) -> str:
    return product_library.resolve_seedance_source(product_id) or WHITE_HERO_BY_PRODUCT.get(product_id, "")


def _run_root(project_id: str, run_root: str | Path | None) -> Path:
    return Path(run_root) if run_root is not None else RUNS_ROOT / project_id


def _load_artifact(root: Path, artifact_name: str) -> dict[str, Any]:
    path = root / "artifacts" / f"{artifact_name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_shot_report(root: Path, project_id: str, new_report: dict[str, Any]) -> None:
    path = root / "artifacts" / "shot_report.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "version": "2.0",
        "project_id": project_id,
        "shots": [],
    }
    by_number = {int(shot["number"]): shot for shot in existing.get("shots", [])}
    for shot in new_report.get("shots", []):
        by_number[int(shot["number"])] = shot
    merged = {
        "version": "2.0",
        "project_id": project_id,
        "shots": [by_number[number] for number in sorted(by_number)],
    }
    artifacts.save_artifact(project_id, "shot_report", merged, run_root=root)


def _all_production_succeeded(project_id: str, *, db_path: str | Path | None) -> bool:
    tasks = [
        task
        for task in queue.list_tasks(project_id=project_id, db_path=db_path)
        if task.stage == "production"
    ]
    return bool(tasks) and all(task.status == "succeeded" for task in tasks)


def _terminal_status(
    project_id: str,
    root: Path,
    *,
    db_path: str | Path | None,
) -> EngineRunStatus | None:
    failed = [
        task
        for task in queue.list_tasks(project_id=project_id, status="failed", db_path=db_path)
        if task.stage == "production"
    ]
    if failed and not _has_queued_production(project_id, db_path=db_path):
        return EngineRunStatus(project_id, "production", "failed", "production has failed shot tasks")
    latest = checkpoint.read_latest(project_id, run_root=root)
    if latest and latest.get("stage") == "archive" and latest.get("status") == "succeeded":
        return EngineRunStatus(project_id, "archive", "succeeded", "pipeline complete")
    return None


def _has_queued_production(project_id: str, *, db_path: str | Path | None) -> bool:
    return any(
        task.stage == "production" and task.status == "queued"
        for task in queue.list_tasks(project_id=project_id, db_path=db_path)
    )


def _requeue_script_or_needs_review(task: queue.Task, root: Path, *, db_path: str | Path | None) -> EngineRunStatus:
    script_tasks = [
        item
        for item in queue.list_tasks(project_id=task.project_id, db_path=db_path)
        if item.stage == "script"
    ]
    if len(script_tasks) <= 2:
        _enqueue_stage(task.project_id, "script", {"run_root": root.as_posix()}, db_path=db_path)
        return EngineRunStatus(task.project_id, "script", "queued", "script review requested rewrite")
    checkpoint.write_checkpoint(task.project_id, "script_review", status="needs_review", run_root=root)
    return EngineRunStatus(task.project_id, "script_review", "needs_review", "script rewrite limit exceeded")
