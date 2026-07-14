from pathlib import Path

from jsonschema import Draft7Validator

from libshared import artifacts


def test_artifact_schema_set_has_twelve_files() -> None:
    schema_files = sorted(Path("schemas/artifacts").glob("*.schema.json"))

    assert [path.name for path in schema_files] == [
        "analysis_report.schema.json",
        "asset_manifest.schema.json",
        "library_index.schema.json",
        "material_meta.schema.json",
        "render_report.schema.json",
        "research_brief.schema.json",
        "review_outputs.schema.json",
        "script_breakdown.schema.json",
        "script_copy.schema.json",
        "shot_plan.schema.json",
        "shot_report.schema.json",
        "strategy_brief.schema.json",
    ]
    for path in schema_files:
        Draft7Validator.check_schema(artifacts.load_schema(path.stem.removesuffix(".schema")))


def test_review_output_aliases_share_schema() -> None:
    for artifact_name in ("review_report", "qa_report", "publish_archive"):
        artifacts.validate_artifact(
            artifact_name,
            {
                "version": "2.0",
                "project_id": "ref-review",
                "artifact_type": artifact_name,
                "status": "PASS",
            },
        )
