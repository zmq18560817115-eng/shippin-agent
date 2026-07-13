from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from libshared import artifacts


def valid_script_copy() -> dict:
    return {
        "version": "2.0",
        "project_id": "ref-a3",
        "product_id": "便携恒温杯",
        "source_link_id": None,
        "total_duration_s": 15,
        "generator": {"provider": "mock", "model": "unit", "prompt_version": "a3"},
        "sections": [
            {
                "number": 1,
                "role": "钩子",
                "timing": "0-3s",
                "voiceover_en": "Night feeds should feel easier.",
                "selling_points": [],
            },
            {
                "number": 2,
                "role": "痛点",
                "timing": "3-6s",
                "voiceover_en": "Cold milk and long waits make bedtime harder.",
                "selling_points": [],
            },
            {
                "number": 3,
                "role": "方案",
                "timing": "6-9s",
                "voiceover_en": "Pour milk into the cup and warm it for bottle prep.",
                "selling_points": ["USB-C rechargeable"],
            },
            {
                "number": 4,
                "role": "证明",
                "timing": "9-12s",
                "voiceover_en": "The compact cup fits your nightstand or bag.",
                "selling_points": ["portable"],
            },
            {
                "number": 5,
                "role": "行动号召",
                "timing": "12-15s",
                "voiceover_en": "Save this for your next night feed.",
                "selling_points": [],
            },
        ],
        "feedback_constraints_applied": [],
    }


def valid_shot_plan() -> dict:
    return {
        "version": "2.0",
        "project_id": "ref-a3",
        "script_copy_ref": "artifacts/script_copy.json",
        "aspect_ratio": "9:16",
        "shots": [
            {
                "number": 1,
                "visual": "Product on a bedside table.",
                "visual_prompt": "soft night bedroom",
                "seedance_prompt": "Product appearance must match the white-background hero reference. Soft night bedroom.",
                "footage_type": "AI_VIDEO",
                "camera_motion": {"type": "dolly_in", "duration_sec": 3},
            },
            {
                "number": 2,
                "visual": "Parent prepares milk near the product.",
                "visual_prompt": "hands only",
                "seedance_prompt": "Product appearance must match the white-background hero reference. Hands-only bottle prep.",
                "footage_type": "AI_BROLL",
                "camera_motion": {"type": "static", "duration_sec": 3},
            },
            {
                "number": 3,
                "visual": "Milk is poured into the cup.",
                "visual_prompt": "pouring action",
                "seedance_prompt": "Product appearance must match the white-background hero reference. Correct pour direction.",
                "footage_type": "AI_VIDEO",
                "camera_motion": {"type": "pan_right", "duration_sec": 3},
            },
            {
                "number": 4,
                "visual": "Cup fits in a bag.",
                "visual_prompt": "product portability",
                "seedance_prompt": "Product appearance must match the white-background hero reference. Bag flat lay.",
                "footage_type": "AI_BROLL",
                "camera_motion": {"type": "static", "duration_sec": 3},
            },
            {
                "number": 5,
                "visual": "CTA product close-up.",
                "visual_prompt": "close-up",
                "seedance_prompt": "Product appearance must match the white-background hero reference. Clean product close-up.",
                "footage_type": "AI_VIDEO",
                "camera_motion": {"type": "dolly_out", "duration_sec": 3},
            },
        ],
    }


def valid_asset_manifest() -> dict:
    return {
        "version": "2.0",
        "project_id": "ref-a3",
        "product_id": "便携恒温杯",
        "seedance_source": "data/01_素材库/产品资料/便携恒温杯/listing-0602-nw/主图/白底主图.png",
        "hero_frames": [
            {"number": 1, "path": "shots/hero_001.png", "source_refs": ["data/01_素材库/产品资料/便携恒温杯/listing-0602-nw/主图/白底主图.png"]},
            {"number": 2, "path": "shots/hero_002.png", "source_refs": ["data/01_素材库/产品资料/便携恒温杯/listing-0602-nw/主图/白底主图.png"]},
            {"number": 3, "path": "shots/hero_003.png", "source_refs": ["data/01_素材库/产品资料/便携恒温杯/listing-0602-nw/主图/白底主图.png"]},
        ],
    }


def assert_invalid(artifact_name: str, payload: dict, pointer: str, **context: dict) -> None:
    with pytest.raises(artifacts.ArtifactValidationError) as excinfo:
        artifacts.validate_artifact(artifact_name, payload, **context)
    assert pointer in str(excinfo.value)


def test_a3_valid_core_artifacts_pass(tmp_path: Path) -> None:
    script = valid_script_copy()
    shot_plan = valid_shot_plan()
    asset_manifest = valid_asset_manifest()

    artifacts.validate_artifact("script_copy", script)
    artifacts.validate_artifact("shot_plan", shot_plan, script_copy=script)
    artifacts.validate_artifact("asset_manifest", asset_manifest)

    saved = artifacts.save_artifact("ref-a3", "script_copy", script, run_root=tmp_path / "ref-a3")
    assert saved == tmp_path / "ref-a3" / "artifacts" / "script_copy.json"
    assert saved.exists()


@pytest.mark.parametrize(
    ("mutate", "pointer"),
    [
        (lambda p: p.pop("version"), "/version"),
        (lambda p: p["sections"][0].pop("voiceover_en"), "/sections/0/voiceover_en"),
        (lambda p: p["sections"].__setitem__(1, {**p["sections"][1], "number": 3}), "/sections/1/number"),
        (lambda p: p["sections"].__setitem__(1, {**p["sections"][1], "timing": "4-7s"}), "/sections/1/timing"),
        (lambda p: p.__setitem__("total_duration_s", 30), "/total_duration_s"),
        (lambda p: p["sections"][0].__setitem__("voiceover_en", "This is the best guaranteed pain-free warmer."), "/sections/0/voiceover_en"),
    ],
)
def test_a3_script_copy_rejects_bad_fixtures(mutate, pointer: str) -> None:
    payload = deepcopy(valid_script_copy())
    mutate(payload)
    assert_invalid("script_copy", payload, pointer)


@pytest.mark.parametrize(
    ("mutate", "pointer"),
    [
        (lambda p: p.pop("script_copy_ref"), "/script_copy_ref"),
        (lambda p: p["shots"][1].__setitem__("number", 9), "/shots"),
        (lambda p: p["shots"][0].__setitem__("camera_motion", {"type": "teleport"}), "/shots/0/camera_motion/type"),
        (lambda p: p["shots"][0].__setitem__("seedance_prompt", ""), "/shots/0/seedance_prompt"),
        (lambda p: p["shots"][0].__setitem__("seedance_prompt", "Soft night bedroom without product lock."), "/shots/0/seedance_prompt"),
    ],
)
def test_a3_shot_plan_rejects_bad_fixtures(mutate, pointer: str) -> None:
    payload = deepcopy(valid_shot_plan())
    mutate(payload)
    assert_invalid("shot_plan", payload, pointer, script_copy=valid_script_copy())


def test_a3_asset_manifest_rejects_scene_image_seedance_source() -> None:
    payload = deepcopy(valid_asset_manifest())
    payload["seedance_source"] = "data/01_素材库/产品资料/便携恒温杯/listing-0602-nw/产品场景使用图/场景图1.jpg"

    assert_invalid("asset_manifest", payload, "/seedance_source")
