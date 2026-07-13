from __future__ import annotations

import json
import os
import re
import secrets
import zipfile
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from libshared import artifacts, checkpoint
from libshared.paths import DATA_ROOT, ROOT, RUNS_ROOT
from orchestrator import cost_tracker, engine, queue
from tools.collect import manual_import


WEB_ROOT = ROOT / "web"
PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,96}$")
ARTIFACT_NAMES = {
    "analysis_report",
    "script_copy",
    "review_report",
    "shot_plan",
    "asset_manifest",
    "shot_report",
    "render_report",
    "qa_report",
    "publish_archive",
}
GATE_STAGES = ("script_gate", "hero_gate")
NODE_STAGES = {
    "collector": (),
    "analysis": ("analysis",),
    "script": ("script",),
    "storyboard": ("storyboard",),
    "asset": ("asset", "hero_gate"),
    "media": ("production", "compose"),
    "review": ("script_review", "script_gate", "final_qa", "archive"),
}
STATUS_PRIORITY = (
    "failed",
    "blocked",
    "needs_review",
    "awaiting_human",
    "running",
    "queued",
    "succeeded",
    "idle",
)


class PipelineRunRequest(BaseModel):
    project_id: str | None = None
    product_id: str = "便携恒温杯"
    source_link_id: int | None = None
    source_material_id: str | None = None
    link_id: str | int | None = None
    mock: bool = True


class ManualCollectRequest(BaseModel):
    links_text: str = ""
    urls: list[str] | None = None
    items: list[dict[str, Any]] | None = None
    product_id: str = "便携恒温杯"
    source_keyword: str = "manual_tiktok"


class GateApproveRequest(BaseModel):
    project_id: str
    stage: str
    approver: str = "operator"
    notes: str | None = None
    mock: bool = True


class GateRewriteRequest(BaseModel):
    project_id: str
    stage: str = "script_gate"
    reason: str | None = None
    mock: bool = True


class HeroRegenRequest(BaseModel):
    project_id: str
    shot_index: int


class TaskRetryRequest(BaseModel):
    project_id: str
    shot_index: int
    mock: bool = True


class FeedbackRequest(BaseModel):
    project_id: str
    text: str
    author: str = "operator"


@asynccontextmanager
async def lifespan(_: FastAPI):
    queue.init_db(db_path=_db_path())
    yield


app = FastAPI(title="video-agent-factory", version="0.0.0", lifespan=lifespan)
if WEB_ROOT.exists():
    app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")


@app.get("/", include_in_schema=False)
def workbench() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    queue.init_db(db_path=_db_path())
    return {"status": "ok"}


@app.get("/api/v2/products")
def products() -> dict[str, list[dict[str, Any]]]:
    return {"items": _list_products()}


@app.post("/api/v2/collect/manual")
def collect_manual(request: ManualCollectRequest) -> dict[str, Any]:
    payload = {
        "links_text": request.links_text,
        "urls": request.urls or [],
        "items": request.items or [],
        "product_id": request.product_id,
        "source_keyword": request.source_keyword,
        "library_root": _material_library_root().as_posix(),
    }
    result = manual_import.execute(payload, context=_tool_context())
    if not result.ok:
        error = result.error or {"message": "manual import failed"}
        status_code = 422 if error.get("category") == "validation" else 500
        raise HTTPException(status_code=status_code, detail=error.get("message") or error)
    queue.record_event(
        event_type="collector.manual_import",
        message=f"{result.data['imported_count']} links",
        meta={"library_root": result.data["library_root"]},
        db_path=_db_path(),
    )
    return result.data


@app.get("/api/v2/collect/library")
def collect_library(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    root = _material_library_root()
    index = manual_import.load_library_index(root)
    items = index.get("items", [])[:limit]
    enriched = []
    for item in items:
        payload = dict(item)
        try:
            meta = manual_import.load_material_meta(str(item["material_id"]), root)
        except (FileNotFoundError, ValueError):
            meta = None
        payload["material_meta"] = meta
        enriched.append(payload)
    return {"library_root": root.as_posix(), "items": enriched}


@app.get("/api/v2/collect/materials/{material_id}")
def collect_material(material_id: str) -> dict[str, Any]:
    try:
        return manual_import.load_material_meta(material_id, _material_library_root())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/v2/pipeline/run")
def run_pipeline(request: PipelineRunRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id or _new_project_id())
    source_link_id = _normalize_source_link_id(request.source_link_id, request.link_id)
    source_meta = _source_material_or_none(request.source_material_id)
    product_id = request.product_id or str((source_meta or {}).get("product_id") or "便携恒温杯")
    run_root = _run_root(project_id)
    task_id = engine.start_pipeline(
        project_id,
        product_id=product_id,
        source_link_id=source_link_id,
        source_material_id=request.source_material_id,
        source_url=str((source_meta or {}).get("source_url") or ""),
        db_path=_db_path(),
        run_root=run_root,
        mock=request.mock,
    )
    status = engine.run_until_blocked(
        project_id,
        db_path=_db_path(),
        run_root=run_root,
        mock=request.mock,
    )
    return {
        "project_id": project_id,
        "task_id": task_id,
        "engine": _engine_status(status),
        "project": _project_summary(project_id),
    }


@app.get("/api/v2/pipeline")
def list_pipeline(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    with queue.get_conn(_db_path()) as conn:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY created_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return {"items": [_project_summary(str(row["id"]), row=row) for row in rows]}


@app.get("/api/v2/pipeline/{project_id}")
def get_pipeline(project_id: str) -> dict[str, Any]:
    return _project_summary(_validate_project_id(project_id))


@app.get("/api/v2/artifacts/{project_id}/{artifact_name}")
def get_artifact(project_id: str, artifact_name: str) -> dict[str, Any]:
    project_id = _validate_project_id(project_id)
    artifact_name = _validate_artifact_name(artifact_name)
    payload = _load_artifact(project_id, artifact_name)
    if artifact_name == "asset_manifest":
        _attach_preview_urls(project_id, payload)
    return payload


@app.put("/api/v2/artifacts/{project_id}/{artifact_name}")
def put_artifact(
    project_id: str,
    artifact_name: str,
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    project_id = _validate_project_id(project_id)
    artifact_name = _validate_artifact_name(artifact_name)
    if artifact_name != "script_copy":
        raise HTTPException(status_code=400, detail="block6 only allows script_copy edits")
    if payload.get("project_id") != project_id:
        raise HTTPException(status_code=400, detail="artifact project_id does not match URL")

    old_payload = _load_artifact_or_none(project_id, artifact_name)
    stale_sections = _changed_script_sections(old_payload, payload)
    try:
        artifacts.save_artifact(project_id, artifact_name, payload, run_root=_run_root(project_id))
    except artifacts.ArtifactValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {"pointer": issue.pointer, "message": issue.message}
                for issue in exc.issues
            ],
        ) from exc

    _refresh_script_gate_checkpoint(project_id, stale_sections)
    queue.record_event(
        project_id=project_id,
        event_type="artifact.saved",
        message=artifact_name,
        meta={"stale_sections": stale_sections},
        db_path=_db_path(),
    )
    return {
        "ok": True,
        "project_id": project_id,
        "artifact_name": artifact_name,
        "stale_sections": stale_sections,
        "artifact": payload,
    }


@app.post("/api/v2/gates/approve")
def approve_gate(request: GateApproveRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id)
    if request.stage not in GATE_STAGES:
        raise HTTPException(status_code=400, detail=f"unknown gate stage: {request.stage}")
    try:
        approved = engine.approve_gate(
            project_id,
            request.stage,
            approver=request.approver,
            notes=request.notes,
            db_path=_db_path(),
            run_root=_run_root(project_id),
        )
        status = engine.run_until_blocked(
            project_id,
            db_path=_db_path(),
            run_root=_run_root(project_id),
            mock=request.mock,
        )
    except checkpoint.GateApprovalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "approved": _engine_status(approved),
        "engine": _engine_status(status),
        "project": _project_summary(project_id),
    }


@app.post("/api/v2/gates/rewrite")
def rewrite_gate(request: GateRewriteRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id)
    if request.stage != "script_gate":
        raise HTTPException(status_code=400, detail="only script_gate can be rewritten")
    root = _run_root(project_id)
    latest_gate = _latest_checkpoint_for_stage(project_id, "script_gate", root)
    if latest_gate is None or latest_gate.get("status") != "awaiting_human":
        raise HTTPException(status_code=409, detail="script_gate is not awaiting human review")

    data = dict(latest_gate.get("data") or {})
    data["rewrite_reason"] = request.reason
    checkpoint.write_checkpoint(
        project_id,
        "script_gate",
        status="needs_review",
        artifacts=dict(latest_gate.get("artifacts") or {}),
        data=data,
        run_root=root,
    )
    queue.enqueue_task(
        project_id=project_id,
        stage="script",
        agent="script",
        task_type="default",
        payload={"run_root": root.as_posix(), "rewrite_reason": request.reason},
        db_path=_db_path(),
    )
    queue.enqueue_task(
        project_id=project_id,
        stage="script_review",
        agent="review",
        task_type="default",
        payload={"run_root": root.as_posix(), "rewrite_reason": request.reason},
        db_path=_db_path(),
    )
    status = engine.run_until_blocked(
        project_id,
        db_path=_db_path(),
        run_root=root,
        mock=request.mock,
    )
    return {"engine": _engine_status(status), "project": _project_summary(project_id)}


@app.post("/api/v2/hero/regen")
def regen_hero(request: HeroRegenRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id)
    if request.shot_index < 1:
        raise HTTPException(status_code=400, detail="shot_index must be >= 1")
    manifest = _load_artifact(project_id, "asset_manifest")
    frame = _find_hero_frame(manifest, request.shot_index)
    frame["status"] = "generated"
    frame["regenerated_at"] = queue.utc_now()
    artifacts.save_artifact(project_id, "asset_manifest", manifest, run_root=_run_root(project_id))
    queue.record_event(
        project_id=project_id,
        event_type="hero.regenerated",
        message=f"shot{request.shot_index}",
        meta={"shot_index": request.shot_index},
        db_path=_db_path(),
    )
    _attach_preview_urls(project_id, manifest)
    return {
        "ok": True,
        "project_id": project_id,
        "shot_index": request.shot_index,
        "asset_manifest": manifest,
    }


@app.post("/api/v2/tasks/retry")
def retry_task(request: TaskRetryRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id)
    try:
        status = engine.retry_failed_shot(
            project_id,
            request.shot_index,
            db_path=_db_path(),
            run_root=_run_root(project_id),
            mock=request.mock,
        )
        if status.status not in {"awaiting_human", "failed", "blocked", "needs_review", "succeeded"}:
            status = engine.run_until_blocked(
                project_id,
                db_path=_db_path(),
                run_root=_run_root(project_id),
                mock=request.mock,
            )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"engine": _engine_status(status), "project": _project_summary(project_id)}


@app.get("/api/v2/runs/{project_id}/{relative_path:path}", include_in_schema=False)
def get_run_file(project_id: str, relative_path: str) -> FileResponse:
    project_id = _validate_project_id(project_id)
    target = _safe_run_file(_run_root(project_id), relative_path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="run file not found")
    return FileResponse(target)


@app.get("/api/v2/download/{project_id}")
def download_project(project_id: str) -> FileResponse:
    project_id = _validate_project_id(project_id)
    zip_path = _build_delivery_zip(project_id)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"{project_id}.zip",
    )


@app.post("/api/v2/feedback")
def write_feedback(request: FeedbackRequest) -> dict[str, Any]:
    project_id = _validate_project_id(request.project_id)
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="feedback text is required")
    if len(text) > 1000:
        raise HTTPException(status_code=400, detail="feedback text is too long")

    feedback_root = _feedback_root()
    feedback_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    path = feedback_root / f"{project_id}-{stamp}-{secrets.token_hex(2)}.json"
    payload = {
        "version": "2.0",
        "project_id": project_id,
        "author": request.author,
        "text": text,
        "created_at": queue.utc_now(),
    }
    _atomic_write_json(path, payload)
    queue.record_event(
        project_id=project_id,
        event_type="feedback.created",
        message=text[:120],
        meta={"path": path.as_posix(), "author": request.author},
        db_path=_db_path(),
    )
    return {"ok": True, "path": str(path), "feedback": payload}


def _db_path() -> Path:
    return queue.resolve_db_path()


def _runs_root() -> Path:
    configured = os.environ.get("VAF_RUNS_ROOT")
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else ROOT / path
    return RUNS_ROOT


def _material_library_root() -> Path:
    configured = os.environ.get("VAF_MATERIAL_LIBRARY_ROOT")
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else ROOT / path
    return DATA_ROOT / "01_素材库" / "对标视频" / "manual_import"


def _feedback_root() -> Path:
    configured = os.environ.get("VAF_FEEDBACK_ROOT")
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else ROOT / path
    return DATA_ROOT / "05_反馈库"


def _tool_context() -> manual_import.ToolContext:
    from tools.base_tool import ToolContext

    return ToolContext.from_mapping(
        {
            "mock": True,
            "env": os.environ,
        }
    )


def _run_root(project_id: str) -> Path:
    row = _project_row_or_none(project_id)
    if row is not None:
        payload = _loads_json(row["payload_json"])
        run_root = payload.get("run_root")
        if run_root:
            return Path(str(run_root))
    return _runs_root() / project_id


def _new_project_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"ref-{stamp}-{secrets.token_hex(3)}"


def _validate_project_id(project_id: str) -> str:
    if not PROJECT_ID_RE.fullmatch(project_id):
        raise HTTPException(status_code=400, detail="invalid project_id")
    return project_id


def _validate_artifact_name(artifact_name: str) -> str:
    if artifact_name not in ARTIFACT_NAMES:
        raise HTTPException(status_code=404, detail="artifact is not registered")
    return artifact_name


def _normalize_source_link_id(source_link_id: int | None, link_id: str | int | None) -> int | None:
    value = source_link_id if source_link_id is not None else link_id
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _project_row_or_none(project_id: str):
    with queue.get_conn(_db_path()) as conn:
        return conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()


def _project_summary(project_id: str, *, row: Any | None = None) -> dict[str, Any]:
    row = row or _project_row_or_none(project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    root = _run_root(project_id)
    payload = _loads_json(row["payload_json"])
    tasks = queue.list_tasks(project_id=project_id, db_path=_db_path())
    checkpoints = checkpoint.read_all(project_id, run_root=root)
    stages = _stage_statuses(tasks, checkpoints)
    pending_gate = _pending_gate(checkpoints)
    current_stage = _current_stage(stages, checkpoints, pending_gate)
    status = _project_status(stages, pending_gate)
    return {
        "project_id": project_id,
        "product_id": row["product_id"],
        "source_link_id": row["source_link_id"],
        "source_material_id": payload.get("source_material_id"),
        "source_url": payload.get("source_url"),
        "status": status,
        "current_stage": current_stage,
        "current_gate": pending_gate,
        "budget_cny": float(row["budget_cny"]),
        "budget_mode": row["budget_mode"],
        "cost": cost_tracker.get_project_cost(project_id, db_path=_db_path()),
        "nodes": _node_statuses(stages),
        "stages": stages,
        "tasks": [_task_to_dict(task) for task in tasks],
        "artifacts": _artifact_presence(project_id, root),
        "latest_checkpoint": checkpoints[-1] if checkpoints else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _stage_statuses(tasks: list[queue.Task], checkpoints: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest_checkpoints: dict[str, dict[str, Any]] = {}
    for item in checkpoints:
        latest_checkpoints[str(item["stage"])] = item

    result: dict[str, dict[str, Any]] = {}
    for stage in checkpoint.STAGE_ORDER:
        stage_tasks = [task for task in tasks if task.stage == stage]
        task_status = _aggregate_status([task.status for task in stage_tasks])
        checkpoint_status = latest_checkpoints.get(stage, {}).get("status")
        status = _aggregate_status([task_status, str(checkpoint_status or "idle")])
        result[stage] = {
            "status": status,
            "task_count": len(stage_tasks),
            "errors": [
                {
                    "task_id": task.id,
                    "stage": task.stage,
                    "agent": task.agent,
                    "shot_index": task.payload_json.get("shot_index"),
                    "error_json": task.error_json,
                }
                for task in stage_tasks
                if task.error_json
            ],
        }
    return result


def _node_statuses(stages: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for agent, stage_names in NODE_STAGES.items():
        statuses = [stages[stage]["status"] for stage in stage_names]
        status = _aggregate_status(statuses)
        nodes.append(
            {
                "agent": agent,
                "status": status,
                "stages": list(stage_names),
            }
        )
    return nodes


def _aggregate_status(statuses: list[str]) -> str:
    values = [status for status in statuses if status and status != "idle"]
    if not values:
        return "idle"
    for status in STATUS_PRIORITY:
        if status in values:
            return status
    return values[0]


def _pending_gate(checkpoints: list[dict[str, Any]]) -> str | None:
    latest_by_stage: dict[str, dict[str, Any]] = {}
    for item in checkpoints:
        latest_by_stage[str(item["stage"])] = item
    for stage in reversed(GATE_STAGES):
        if latest_by_stage.get(stage, {}).get("status") == "awaiting_human":
            return stage
    return None


def _current_stage(
    stages: dict[str, dict[str, Any]],
    checkpoints: list[dict[str, Any]],
    pending_gate: str | None,
) -> str | None:
    if pending_gate:
        return pending_gate
    for stage, item in stages.items():
        if item["status"] in {"failed", "blocked", "needs_review"}:
            return stage
    for stage in checkpoint.STAGE_ORDER:
        if stages[stage]["status"] in {"running", "queued"}:
            return stage
    if checkpoints:
        return str(checkpoints[-1]["stage"])
    return None


def _source_material_or_none(material_id: str | None) -> dict[str, Any] | None:
    if not material_id:
        return None
    try:
        return manual_import.load_material_meta(material_id, _material_library_root())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _project_status(stages: dict[str, dict[str, Any]], pending_gate: str | None) -> str:
    if pending_gate:
        return "awaiting_human"
    if stages["archive"]["status"] == "succeeded":
        return "succeeded"
    status = _aggregate_status([item["status"] for item in stages.values()])
    return "running" if status in {"queued", "running"} else status


def _artifact_presence(project_id: str, run_root: Path) -> dict[str, bool]:
    artifact_dir = run_root / "artifacts"
    return {
        name: (artifact_dir / f"{name}.json").is_file()
        for name in sorted(ARTIFACT_NAMES)
    }


def _task_to_dict(task: queue.Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "stage": task.stage,
        "agent": task.agent,
        "task_type": task.task_type,
        "status": task.status,
        "attempt": task.attempt,
        "max_retries": task.max_retries,
        "payload_json": task.payload_json,
        "error_json": task.error_json,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "finished_at": task.finished_at,
    }


def _engine_status(status: engine.EngineRunStatus) -> dict[str, Any]:
    return {
        "project_id": status.project_id,
        "stage": status.stage,
        "status": status.status,
        "message": status.message,
    }


def _load_artifact(project_id: str, artifact_name: str) -> dict[str, Any]:
    path = _artifact_path(project_id, artifact_name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"{artifact_name} not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_artifact_or_none(project_id: str, artifact_name: str) -> dict[str, Any] | None:
    path = _artifact_path(project_id, artifact_name)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_path(project_id: str, artifact_name: str) -> Path:
    return _run_root(project_id) / "artifacts" / f"{artifact_name}.json"


def _changed_script_sections(
    old_payload: dict[str, Any] | None,
    new_payload: dict[str, Any],
) -> list[int]:
    if old_payload is None:
        return [int(section["number"]) for section in new_payload.get("sections", [])]
    old_by_number = {
        int(section["number"]): section
        for section in old_payload.get("sections", [])
        if "number" in section
    }
    changed: list[int] = []
    for section in new_payload.get("sections", []):
        number = int(section["number"])
        old_section = old_by_number.get(number)
        if old_section is None:
            changed.append(number)
            continue
        if (
            old_section.get("voiceover_en") != section.get("voiceover_en")
            or old_section.get("timing") != section.get("timing")
        ):
            changed.append(number)
    return changed


def _refresh_script_gate_checkpoint(project_id: str, stale_sections: list[int]) -> None:
    root = _run_root(project_id)
    latest_gate = _latest_checkpoint_for_stage(project_id, "script_gate", root)
    if latest_gate is None or latest_gate.get("status") != "awaiting_human":
        return
    artifact_refs = dict(latest_gate.get("artifacts") or {})
    artifact_refs["script_copy"] = "artifacts/script_copy.json"
    if (root / "artifacts" / "review_report.json").is_file():
        artifact_refs["review_report"] = "artifacts/review_report.json"
    data = dict(latest_gate.get("data") or {})
    data["stale_sections"] = stale_sections
    checkpoint.write_checkpoint(
        project_id,
        "script_gate",
        status="awaiting_human",
        artifacts=artifact_refs,
        data=data,
        run_root=root,
    )


def _latest_checkpoint_for_stage(project_id: str, stage: str, run_root: Path) -> dict[str, Any] | None:
    for item in reversed(checkpoint.read_all(project_id, run_root=run_root)):
        if item.get("stage") == stage:
            return item
    return None


def _find_hero_frame(manifest: dict[str, Any], shot_index: int) -> dict[str, Any]:
    for frame in manifest.get("hero_frames", []):
        if int(frame.get("number", 0)) == shot_index:
            return frame
    raise HTTPException(status_code=404, detail=f"hero frame not found for shot {shot_index}")


def _attach_preview_urls(project_id: str, manifest: dict[str, Any]) -> None:
    run_root = _run_root(project_id)
    for frame in manifest.get("hero_frames", []):
        path_text = str(frame.get("path") or "")
        path = Path(path_text)
        try:
            relative = path.resolve().relative_to(run_root.resolve()).as_posix()
        except ValueError:
            relative = f"shots/{path.name}"
        frame["preview_url"] = f"/api/v2/runs/{project_id}/{relative}"


def _safe_run_file(run_root: Path, relative_path: str) -> Path:
    candidate = (run_root / relative_path).resolve()
    try:
        candidate.relative_to(run_root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid run file path") from exc
    return candidate


def _build_delivery_zip(project_id: str) -> Path:
    run_root = _run_root(project_id)
    if not run_root.exists():
        raise HTTPException(status_code=404, detail="run not found")
    delivery_dir = run_root / "delivery"
    delivery_dir.mkdir(parents=True, exist_ok=True)
    zip_path = delivery_dir / f"{project_id}.zip"
    files = [
        path
        for path in run_root.rglob("*")
        if path.is_file() and path.resolve() != zip_path.resolve()
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(run_root).as_posix())
    return zip_path


def _list_products() -> list[dict[str, Any]]:
    materials_root = DATA_ROOT / "01_素材库" / "产品资料"
    items: list[dict[str, Any]] = []
    if materials_root.exists():
        for product_doc in sorted(materials_root.glob("*.md")):
            product_id = product_doc.stem
            product_dir = materials_root / product_id
            has_white_hero = bool(list(product_dir.rglob("白底主图.*"))) if product_dir.exists() else False
            items.append({"id": product_id, "label": product_id, "ready": has_white_hero})
    if not items:
        items.append({"id": "便携恒温杯", "label": "便携恒温杯", "ready": True})
    return sorted(items, key=lambda item: (not item["ready"], item["label"]))


def _loads_json(value: str | bytes | None) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)
