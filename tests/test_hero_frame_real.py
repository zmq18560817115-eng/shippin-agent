from __future__ import annotations

from pathlib import Path

from tools.base_tool import ToolContext
from tools.video import hero_frame


def test_real_hero_frames_are_materialized(tmp_path: Path) -> None:
    source = tmp_path / "白底主图.png"
    source.write_bytes(b"approved-product-image")
    run_root = tmp_path / "run"
    result = hero_frame.execute(
        {
            "project_id": "hero-real",
            "product_id": "便携恒温杯",
            "seedance_source": str(source),
            "shot_plan": {"shots": [{"number": 1}, {"number": 2}]},
        },
        ToolContext.from_mapping({"mock": False, "run_root": str(run_root)}),
    )
    assert result.ok
    for frame in result.data["asset_manifest"]["hero_frames"]:
        path = Path(frame["path"])
        assert path.is_absolute()
        assert path.read_bytes() == source.read_bytes()


def test_real_hero_frame_blocks_missing_source(tmp_path: Path) -> None:
    result = hero_frame.execute(
        {
            "project_id": "hero-missing",
            "product_id": "便携恒温杯",
            "seedance_source": str(tmp_path / "missing.png"),
            "shot_plan": {"shots": [{"number": 1}]},
        },
        ToolContext.from_mapping({"mock": False, "run_root": str(tmp_path / "run")}),
    )
    assert not result.ok
    assert "not found" in result.error["message"]
