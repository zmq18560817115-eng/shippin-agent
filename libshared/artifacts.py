from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator, ValidationError

from libshared.paths import RUNS_ROOT


SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas" / "artifacts"
REVIEW_OUTPUT_NAMES = {"review_report", "qa_report", "publish_archive"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
FORBIDDEN_TERMS = (
    "medical grade",
    "pain-free",
    "painless",
    "increase milk supply",
    "boost lactation",
    "cure",
    "treat",
    "diagnose",
    "best",
    "#1",
    "guaranteed",
    "fda approved",
    "completely silent",
    "通乳",
    "催奶",
    "下奶",
)
PRODUCT_APPEARANCE_LOCK_TERMS = (
    "white-background hero",
    "white background hero",
    "白底主图",
    "product appearance must match",
)


@dataclass(frozen=True)
class ArtifactValidationIssue:
    pointer: str
    message: str


class ArtifactValidationError(ValueError):
    def __init__(self, artifact_name: str, issues: list[ArtifactValidationIssue]) -> None:
        self.artifact_name = artifact_name
        self.issues = issues
        joined = "; ".join(f"{issue.pointer}: {issue.message}" for issue in issues)
        super().__init__(f"{artifact_name} validation failed: {joined}")


def validate_artifact(
    artifact_name: str,
    payload: dict[str, Any],
    *,
    script_copy: dict[str, Any] | None = None,
) -> None:
    issues = _validate_schema(artifact_name, payload)
    if not issues:
        issues.extend(_validate_semantics(artifact_name, payload, script_copy=script_copy))
    if issues:
        raise ArtifactValidationError(artifact_name, issues)


def save_artifact(
    project_id: str,
    artifact_name: str,
    payload: dict[str, Any],
    *,
    run_root: str | os.PathLike[str] | None = None,
    script_copy: dict[str, Any] | None = None,
) -> Path:
    validate_artifact(artifact_name, payload, script_copy=script_copy)
    root = Path(run_root) if run_root is not None else RUNS_ROOT / project_id
    artifact_dir = root / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    target = artifact_dir / f"{artifact_name}.json"
    _atomic_write_json(target, payload)
    return target


def load_schema(artifact_name: str) -> dict[str, Any]:
    schema_path = _schema_path_for(artifact_name)
    if not schema_path.exists():
        raise KeyError(f"schema not found for artifact: {artifact_name}")
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _validate_schema(artifact_name: str, payload: dict[str, Any]) -> list[ArtifactValidationIssue]:
    validator = Draft7Validator(load_schema(artifact_name))
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    return [_issue_from_jsonschema(error) for error in errors]


def _validate_semantics(
    artifact_name: str,
    payload: dict[str, Any],
    *,
    script_copy: dict[str, Any] | None,
) -> list[ArtifactValidationIssue]:
    if artifact_name == "script_copy":
        return _validate_script_copy(payload)
    if artifact_name == "shot_plan":
        return _validate_shot_plan(payload, script_copy=script_copy)
    if artifact_name == "asset_manifest":
        return _validate_asset_manifest(payload)
    return []


def _validate_script_copy(payload: dict[str, Any]) -> list[ArtifactValidationIssue]:
    issues: list[ArtifactValidationIssue] = []
    sections = payload.get("sections") or []
    expected_start = 0
    total_duration = payload.get("total_duration_s")

    for index, section in enumerate(sections):
        expected_number = index + 1
        if section.get("number") != expected_number:
            issues.append(
                ArtifactValidationIssue(
                    f"/sections/{index}/number",
                    f"number must be continuous from 1; expected {expected_number}",
                )
            )

        timing = section.get("timing")
        if isinstance(timing, str):
            parsed = _parse_timing(timing)
            if parsed is None:
                issues.append(ArtifactValidationIssue(f"/sections/{index}/timing", "invalid timing"))
            else:
                start, end = parsed
                if start != expected_start:
                    issues.append(
                        ArtifactValidationIssue(
                            f"/sections/{index}/timing",
                            f"timing must be continuous; expected start {expected_start}s",
                        )
                    )
                if end <= start:
                    issues.append(
                        ArtifactValidationIssue(
                            f"/sections/{index}/timing",
                            "timing end must be greater than start",
                        )
                    )
                expected_start = end

        voiceover = str(section.get("voiceover_en") or "")
        forbidden = _find_forbidden_term(voiceover)
        if forbidden:
            issues.append(
                ArtifactValidationIssue(
                    f"/sections/{index}/voiceover_en",
                    f"forbidden compliance term: {forbidden}",
                )
            )

    if isinstance(total_duration, (int, float)) and sections:
        if abs(expected_start - float(total_duration)) > 1:
            issues.append(
                ArtifactValidationIssue(
                    "/total_duration_s",
                    f"timing total {expected_start}s must match total_duration_s within ±1s",
                )
            )

    return issues


def _validate_shot_plan(
    payload: dict[str, Any],
    *,
    script_copy: dict[str, Any] | None,
) -> list[ArtifactValidationIssue]:
    issues: list[ArtifactValidationIssue] = []
    shots = payload.get("shots") or []
    shot_numbers = [shot.get("number") for shot in shots]

    if script_copy is not None:
        section_numbers = [section.get("number") for section in script_copy.get("sections", [])]
        if sorted(shot_numbers) != sorted(section_numbers):
            issues.append(
                ArtifactValidationIssue(
                    "/shots",
                    "shots[].number set must match script_copy.sections[].number",
                )
            )

    for index, shot in enumerate(shots):
        footage_type = shot.get("footage_type")
        if footage_type in {"AI_BROLL", "AI_VIDEO"}:
            prompt = str(shot.get("seedance_prompt") or "").strip()
            if not prompt:
                issues.append(
                    ArtifactValidationIssue(
                        f"/shots/{index}/seedance_prompt",
                        "AI footage requires seedance_prompt",
                    )
                )
            elif not _contains_product_appearance_lock(prompt):
                issues.append(
                    ArtifactValidationIssue(
                        f"/shots/{index}/seedance_prompt",
                        "AI footage prompt must contain product appearance constraint from white-background hero",
                    )
                )

    return issues


def _validate_asset_manifest(payload: dict[str, Any]) -> list[ArtifactValidationIssue]:
    issues: list[ArtifactValidationIssue] = []
    source = str(payload.get("seedance_source") or "")
    if not _is_white_background_hero(source):
        issues.append(
            ArtifactValidationIssue(
                "/seedance_source",
                "seedance_source must point to 白底主图.* and never scene/KV/倒出口 assets",
            )
        )
    return issues


def _schema_path_for(artifact_name: str) -> Path:
    schema_name = "review_outputs" if artifact_name in REVIEW_OUTPUT_NAMES else artifact_name
    return SCHEMA_ROOT / f"{schema_name}.schema.json"


def _issue_from_jsonschema(error: ValidationError) -> ArtifactValidationIssue:
    pointer = _json_pointer(error)
    return ArtifactValidationIssue(pointer, error.message)


def _json_pointer(error: ValidationError) -> str:
    path = list(error.absolute_path)
    if error.validator == "required":
        missing = _missing_required_property(error)
        if missing:
            path.append(missing)
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in path)


def _missing_required_property(error: ValidationError) -> str | None:
    match = re.match(r"'([^']+)' is a required property", error.message)
    return match.group(1) if match else None


def _parse_timing(value: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"(\d+)-(\d+)s", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _find_forbidden_term(text: str) -> str | None:
    lowered = text.casefold()
    for term in FORBIDDEN_TERMS:
        term_lower = term.casefold()
        if re.search(rf"(?<![A-Za-z0-9#]){re.escape(term_lower)}(?![A-Za-z0-9])", lowered):
            return term
    return None


def _contains_product_appearance_lock(text: str) -> bool:
    lowered = text.casefold()
    return any(term.casefold() in lowered for term in PRODUCT_APPEARANCE_LOCK_TERMS)


def _is_white_background_hero(path_text: str) -> bool:
    normalized = path_text.replace("\\", "/").casefold()
    suffix = Path(path_text).suffix.casefold()
    if suffix not in IMAGE_SUFFIXES:
        return False
    if "白底主图" not in normalized:
        return False
    forbidden_markers = ("场景", "产品场景", "m端", "副图", "kv", "倒出口")
    return not any(marker in normalized for marker in forbidden_markers)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)
