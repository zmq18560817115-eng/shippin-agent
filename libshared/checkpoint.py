from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from libshared.paths import RUNS_ROOT


STAGE_ORDER = [
    "analysis",
    "research",
    "strategy",
    "script",
    "script_breakdown",
    "script_review",
    "script_gate",
    "storyboard",
    "asset",
    "hero_gate",
    "production",
    "compose",
    "final_qa",
    "archive",
]


class CheckpointError(Exception):
    """Base checkpoint error."""


class GateApprovalError(CheckpointError):
    """Raised when a human gate cannot be approved from the current state."""


def write_checkpoint(
    project_id: str,
    stage: str,
    *,
    status: str,
    run_root: str | os.PathLike[str] | None = None,
    artifacts: dict[str, str] | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if stage not in STAGE_ORDER:
        raise ValueError(f"unknown stage: {stage}")
    root = _resolve_run_root(project_id, run_root)
    pipeline_dir = root / "pipeline"
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    seq = _next_seq(pipeline_dir)
    checkpoint = {
        "version": "2.0",
        "project_id": project_id,
        "seq": seq,
        "stage": stage,
        "status": status,
        "artifacts": artifacts or {},
        "data": data or {},
    }
    _atomic_write_json(pipeline_dir / f"{seq:06d}_{stage}.json", checkpoint)
    return checkpoint


def read_latest(
    project_id: str,
    *,
    run_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    checkpoints = read_all(project_id, run_root=run_root)
    return checkpoints[-1] if checkpoints else None


def read_all(
    project_id: str,
    *,
    run_root: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    root = _resolve_run_root(project_id, run_root)
    pipeline_dir = root / "pipeline"
    if not pipeline_dir.exists():
        return []
    checkpoints: list[dict[str, Any]] = []
    for path in sorted(pipeline_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("project_id") == project_id:
            checkpoints.append(payload)
    checkpoints.sort(key=lambda item: int(item["seq"]))
    return checkpoints


def get_completed_stages(
    project_id: str,
    *,
    run_root: str | os.PathLike[str] | None = None,
) -> list[str]:
    latest_by_stage: dict[str, dict[str, Any]] = {}
    for item in read_all(project_id, run_root=run_root):
        latest_by_stage[item["stage"]] = item
    return [
        stage
        for stage in STAGE_ORDER
        if latest_by_stage.get(stage, {}).get("status") == "succeeded"
    ]


def get_next_stage(
    project_id: str,
    *,
    run_root: str | os.PathLike[str] | None = None,
) -> str | None:
    completed = set(get_completed_stages(project_id, run_root=run_root))
    for stage in STAGE_ORDER:
        if stage not in completed:
            return stage
    return None


def approve_gate(
    project_id: str,
    stage: str,
    *,
    approver: str,
    notes: str | None = None,
    run_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    latest = _latest_for_stage(project_id, stage, run_root=run_root)
    if latest is None:
        raise GateApprovalError(f"no checkpoint exists for gate stage: {stage}")
    if latest.get("status") != "awaiting_human":
        raise GateApprovalError(
            f"gate {stage} is {latest.get('status')}, not awaiting_human"
        )
    data = dict(latest.get("data") or {})
    data.update({"approved_by": approver, "approval_notes": notes})
    approved = write_checkpoint(
        project_id,
        stage,
        status="succeeded",
        artifacts=dict(latest.get("artifacts") or {}),
        data=data,
        run_root=run_root,
    )
    approved["approved_by"] = approver
    approved["approval_notes"] = notes
    return approved


def resolve_artifact(
    project_id: str,
    artifact_name: str,
    *,
    run_root: str | os.PathLike[str] | None = None,
) -> Path | None:
    for item in reversed(read_all(project_id, run_root=run_root)):
        artifact_rel = (item.get("artifacts") or {}).get(artifact_name)
        if artifact_rel:
            return _resolve_run_root(project_id, run_root) / artifact_rel
    return None


def _latest_for_stage(
    project_id: str,
    stage: str,
    *,
    run_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    for item in reversed(read_all(project_id, run_root=run_root)):
        if item.get("stage") == stage:
            return item
    return None


def _resolve_run_root(project_id: str, run_root: str | os.PathLike[str] | None) -> Path:
    if run_root is not None:
        return Path(run_root)
    return RUNS_ROOT / project_id


def _next_seq(pipeline_dir: Path) -> int:
    max_seq = 0
    for path in pipeline_dir.glob("*.json"):
        prefix = path.name.split("_", 1)[0]
        if prefix.isdigit():
            max_seq = max(max_seq, int(prefix))
    return max_seq + 1


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)
