from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from libshared import artifacts
from libshared.paths import ROOT
from tools.base_tool import ToolContext, ToolResult
from tools.collect import product_library
from tools.tool_registry import register_tool


@register_tool("hero_frame")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    project_id = str(payload.get("project_id") or "ref-mock")
    product_id = str(payload.get("product_id") or "便携恒温杯")
    shot_plan = payload.get("shot_plan") or {"shots": []}
    seedance_source = str(payload.get("seedance_source") or "")
    if not seedance_source:
        return ToolResult.failure("validation", "seedance_source is required")

    run_root = (context.run_root or (ROOT / "data" / "runs" / project_id)).resolve()
    shots_dir = run_root / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    source_path = _resolve_path(seedance_source)
    if not source_path.is_file():
        return ToolResult.failure("validation", f"seedance_source file not found: {seedance_source}")
    hero_frames = []
    for shot in shot_plan.get("shots", []):
        number = int(shot["number"])
        target = shots_dir / f"hero_{number:03d}{source_path.suffix or '.png'}"
        shutil.copy2(source_path, target)
        if not target.is_file() or target.stat().st_size == 0:
            return ToolResult.failure("filesystem", f"hero frame copy failed: {target}")
        hero_frames.append(
            {
                "number": number,
                "path": target.as_posix(),
                "source_refs": [seedance_source],
                "status": "generated",
            }
        )

    manifest = {
        "version": "2.0",
        "project_id": project_id,
        "product_id": product_id,
        "seedance_source": seedance_source,
        "reference_paths": product_library.resolve_generation_references(product_id),
        "hero_frames": hero_frames,
    }
    artifacts.validate_artifact("asset_manifest", manifest)
    return ToolResult.success(
        {"asset_manifest": manifest},
        meta={"tool": "hero_frame", "mock": context.mock, "hero_frame_count": len(hero_frames)},
    )


def _resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else ROOT / path
