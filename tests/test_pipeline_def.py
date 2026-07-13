from pathlib import Path

import yaml


EXPECTED_STAGE_ORDER = [
    "analysis",
    "script",
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


def test_viral_imitate_v2_stage_order() -> None:
    definition = yaml.safe_load(
        Path("pipeline_defs/viral-imitate.yaml").read_text(encoding="utf-8")
    )

    assert definition["name"] == "viral-imitate"
    assert definition["version"] == "2.0"
    assert [stage["name"] for stage in definition["stages"]] == EXPECTED_STAGE_ORDER
    assert definition["stages"][7]["task_type"] == "shot_gen"
