"""分镜关键帧确认闸门（Higgsfield 式：先构图、再动起来）。"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .camera_motion import motion_summary_zh
from .workflow import _load_pack, seedance_status


def hero_frame_gate_enabled() -> bool:
    return os.getenv("HERO_FRAME_GATE", "0").strip().lower() in ("1", "true", "yes")


def pipeline_state_path(project: Path) -> Path:
    meta = project / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    return meta / "pipeline-state.json"


def load_pipeline_state(project: Path) -> dict[str, Any]:
    path = pipeline_state_path(project)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_pipeline_state(project: Path, state: dict[str, Any]) -> None:
    path = pipeline_state_path(project)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def is_hero_frames_confirmed(project: Path) -> bool:
    if not hero_frame_gate_enabled():
        return True
    return bool(load_pipeline_state(project).get("hero_frames_confirmed_at"))


def _hero_dest(project: Path, number: int, src: Path) -> Path:
    broll = project / "broll"
    broll.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower() if src.suffix else ".jpg"
    return broll / f"hero-shot-{number}{suffix}"


def generate_hero_frames(project: Path, *, clear_confirm: bool = True) -> dict[str, Any]:
    """从各镜 I2V 参考图生成静态关键帧预览（不调用 SeedDance）。"""
    from .product_staging import is_fixed_product, resolved_i2v_image_ref

    status = seedance_status(project)
    shots = status.get("shots") or []
    pack = _load_pack(project)
    pack_by_num = {
        int(row.get("number", index + 1)): row
        for index, row in enumerate(pack.get("storyboard") or [])
    }
    brief = {}
    brief_path = project / "localization-brief.yaml"
    if brief_path.is_file():
        try:
            import yaml

            brief = yaml.safe_load(brief_path.read_text(encoding="utf-8")) or {}
        except Exception:
            brief = {}
    product_id = str(brief.get("sku") or "便携恒温杯").strip()
    locked_ref = resolved_i2v_image_ref(project, product_id) if is_fixed_product(product_id) else None

    hero_shots: list[dict[str, Any]] = []
    for shot in shots:
        number = int(shot["number"])
        pack_shot = pack_by_num.get(number, {})
        ref_rel = locked_ref or shot.get("image_ref")
        hero_file: str | None = None
        ready = False
        if ref_rel:
            src = project / str(ref_rel)
            if src.is_file():
                dest = _hero_dest(project, number, src)
                shutil.copy2(src, dest)
                hero_file = dest.relative_to(project).as_posix()
                ready = True
        hero_shots.append(
            {
                "number": number,
                "role": shot.get("role", ""),
                "timing": shot.get("timing", ""),
                "visual": shot.get("visual", ""),
                "motion_summary": motion_summary_zh(pack_shot),
                "image_ref": ref_rel,
                "hero_file": hero_file,
                "ready": ready,
            }
        )

    state = load_pipeline_state(project)
    if clear_confirm:
        state.pop("hero_frames_confirmed_at", None)
    state["hero_frames"] = hero_shots
    state["hero_frames_generated_at"] = datetime.now(timezone.utc).isoformat()
    save_pipeline_state(project, state)
    return hero_frames_status(project)


def hero_frames_status(project: Path) -> dict[str, Any]:
    state = load_pipeline_state(project)
    shots = list(state.get("hero_frames") or [])
    for row in shots:
        number = int(row.get("number") or 0)
        hero_rel = row.get("hero_file")
        if hero_rel and (project / hero_rel).is_file():
            row["ready"] = True
        elif number:
            for path in (project / "broll").glob(f"hero-shot-{number}.*"):
                row["hero_file"] = path.relative_to(project).as_posix()
                row["ready"] = True
                break
    confirmed_at = state.get("hero_frames_confirmed_at")
    all_ready = bool(shots) and all(s.get("ready") for s in shots)
    return {
        "gate_enabled": hero_frame_gate_enabled(),
        "confirmed": bool(confirmed_at),
        "confirmed_at": confirmed_at,
        "generated_at": state.get("hero_frames_generated_at"),
        "shots": shots,
        "all_ready": all_ready,
    }


def confirm_hero_frames(project: Path) -> dict[str, Any]:
    status = hero_frames_status(project)
    if not status["shots"]:
        raise ValueError("尚未生成关键帧，请先生成关键帧预览")
    if not status["all_ready"]:
        missing = [s["number"] for s in status["shots"] if not s.get("ready")]
        raise ValueError(f"镜 {missing} 缺少关键帧参考图")
    state = load_pipeline_state(project)
    state["hero_frames_confirmed_at"] = datetime.now(timezone.utc).isoformat()
    save_pipeline_state(project, state)
    return hero_frames_status(project)


def regenerate_hero_frame(project: Path, shot_number: int) -> dict[str, Any]:
    number = int(shot_number)
    status = seedance_status(project)
    target = next((s for s in status.get("shots") or [] if int(s["number"]) == number), None)
    if not target:
        raise ValueError(f"镜 {number} 不存在或无需生成视频")

    pack = _load_pack(project)
    pack_by_num = {
        int(row.get("number", index + 1)): row
        for index, row in enumerate(pack.get("storyboard") or [])
    }
    pack_shot = pack_by_num.get(number, {})

    ref_rel = target.get("image_ref")
    hero_file: str | None = None
    ready = False
    if ref_rel:
        src = project / str(ref_rel)
        if src.is_file():
            dest = _hero_dest(project, number, src)
            shutil.copy2(src, dest)
            hero_file = dest.relative_to(project).as_posix()
            ready = True

    state = load_pipeline_state(project)
    shots = list(state.get("hero_frames") or [])
    updated = {
        "number": number,
        "role": target.get("role", ""),
        "timing": target.get("timing", ""),
        "visual": target.get("visual", ""),
        "motion_summary": motion_summary_zh(pack_shot),
        "image_ref": ref_rel,
        "hero_file": hero_file,
        "ready": ready,
    }
    replaced = False
    for index, row in enumerate(shots):
        if int(row.get("number") or 0) == number:
            shots[index] = updated
            replaced = True
            break
    if not replaced:
        shots.append(updated)
    state["hero_frames"] = shots
    state.pop("hero_frames_confirmed_at", None)
    save_pipeline_state(project, state)
    return hero_frames_status(project)
