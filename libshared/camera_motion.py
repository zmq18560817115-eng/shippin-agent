"""结构化运镜（Higgsfield 式）— storyboard.camera_motion 与 SeedDance prompt 前缀。"""
from __future__ import annotations

import math
from typing import Any

CAMERA_MOTION_TYPES = (
    "dolly_in",
    "dolly_out",
    "pan_left",
    "pan_right",
    "static",
    "arc",
    "crash_zoom",
)

CAMERA_MOTION_LABELS_ZH: dict[str, str] = {
    "dolly_in": "推近",
    "dolly_out": "拉远",
    "pan_left": "左摇",
    "pan_right": "右摇",
    "static": "固定",
    "arc": "环绕",
    "crash_zoom": "急推",
}

DEFAULT_MOTION_BY_ROLE: dict[str, str] = {
    "钩子": "dolly_in",
    "痛点": "static",
    "方案": "dolly_in",
    "证明": "crash_zoom",
    "行动号召": "static",
}

MOTION_PROMPT_EN: dict[str, str] = {
    "dolly_in": "slow dolly in,",
    "dolly_out": "slow dolly out,",
    "pan_left": "smooth pan left,",
    "pan_right": "smooth pan right,",
    "static": "locked-off static camera,",
    "arc": "gentle arc orbit around subject,",
    "crash_zoom": "fast crash zoom in,",
}


def normalize_motion_type(raw: str | None, *, role: str = "") -> str:
    key = str(raw or "").strip().lower().replace("-", "_")
    if key in CAMERA_MOTION_TYPES:
        return key
    if role:
        return DEFAULT_MOTION_BY_ROLE.get(role.strip(), "static")
    return "static"


def default_camera_motion(role: str, *, duration_sec: int = 4) -> dict[str, Any]:
    motion_type = normalize_motion_type(None, role=role)
    return {
        "type": motion_type,
        "start_frame_focus": "",
        "end_frame_focus": "",
        "duration_sec": duration_sec,
    }


def ensure_shot_camera_motion(shot: dict[str, Any], *, default_duration: int = 4) -> dict[str, Any]:
    role = str(shot.get("role") or "")
    raw = shot.get("camera_motion")
    if isinstance(raw, dict) and raw.get("type"):
        motion = {
            "type": normalize_motion_type(str(raw.get("type")), role=role),
            "start_frame_focus": str(raw.get("start_frame_focus") or "").strip(),
            "end_frame_focus": str(raw.get("end_frame_focus") or "").strip(),
            "duration_sec": int(raw.get("duration_sec") or default_duration),
        }
    else:
        motion = default_camera_motion(role, duration_sec=default_duration)
    shot["camera_motion"] = motion
    return shot


def motion_summary_zh(shot: dict[str, Any]) -> str:
    motion = shot.get("camera_motion") if isinstance(shot.get("camera_motion"), dict) else {}
    mtype = normalize_motion_type(motion.get("type"), role=str(shot.get("role") or ""))
    label = CAMERA_MOTION_LABELS_ZH.get(mtype, mtype)
    role = str(shot.get("role") or "").strip()
    dur = motion.get("duration_sec") or ""
    parts = [label]
    if role:
        parts.append(role)
    if dur:
        parts.append(f"{dur}s")
    return " · ".join(parts)


def motion_prompt_prefix(shot: dict[str, Any]) -> str:
    motion = shot.get("camera_motion") if isinstance(shot.get("camera_motion"), dict) else {}
    mtype = normalize_motion_type(motion.get("type"), role=str(shot.get("role") or ""))
    return MOTION_PROMPT_EN.get(mtype, MOTION_PROMPT_EN["static"])


def apply_motion_to_seedance_prompt(prompt: str, shot: dict[str, Any]) -> str:
    prefix = motion_prompt_prefix(shot).strip()
    text = (prompt or "").strip()
    if not prefix:
        return text
    low = text.lower()
    if any(k in low for k in ("dolly", "pan ", "crash zoom", "locked-off", "orbit", "push-in", "push in", "zoom in")):
        return text
    return f"{prefix} {text}".strip() if text else prefix.rstrip(",")
