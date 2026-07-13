from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from libshared import checkpoint
from libshared.paths import ROOT
from orchestrator import cost_tracker, engine, queue
from tools.collect import manual_import


DEFAULT_REPORT = ROOT / "scripts" / "accept" / "report_10videos.md"
REQUIRED_REAL_ENV = ("DOUBAO_API_KEY", "SEEDANCE_API_KEY")
SAMPLE_LINKS = [
    f"https://www.tiktok.com/@a8-check/video/71000000000000000{index:02d}"
    for index in range(1, 11)
]


@dataclass(frozen=True)
class VideoResult:
    project_id: str
    material_id: str
    status: str
    script_gate_passes: int
    hero_gate_passes: int
    final_qa_status: str
    business_status: str
    cost_cny: float
    elapsed_s: float
    render_path: str
    risks: list[str]

    @property
    def qualified(self) -> bool:
        return (
            self.status == "succeeded"
            and self.final_qa_status == "PASS"
            and self.business_status == "accepted"
            and self.script_gate_passes <= 2
            and self.hero_gate_passes <= 1
            and not any(risk.startswith("BLOCKED") for risk in self.risks)
        )


def run_a8_batch(
    *,
    count: int = 10,
    product_id: str = "便携恒温杯",
    mock: bool = True,
    links: list[str] | None = None,
    db_path: Path | None = None,
    runs_root: Path | None = None,
    material_root: Path | None = None,
    report_path: Path = DEFAULT_REPORT,
    business_status: str = "accepted",
) -> dict[str, Any]:
    db_path = db_path or ROOT / "db" / "agentflow.db"
    runs_root = runs_root or ROOT / "data" / "runs"
    material_root = material_root or manual_import.default_library_root()
    queue.init_db(db_path=db_path)

    selected_links = (links or SAMPLE_LINKS)[:count]
    readiness = real_readiness()
    if not mock and readiness["status"] != "ready":
        report = {
            "mode": "real",
            "status": "BLOCKED",
            "readiness": readiness,
            "results": [],
            "qualified_count": 0,
            "total_count": count,
        }
        write_report(report_path, report)
        return report

    imported = manual_import.import_links(
        [{"url": url} for url in selected_links],
        product_id=product_id,
        source_keyword="a8_cutover",
        library_root=material_root,
    )

    results: list[VideoResult] = []
    for index, item in enumerate(imported["items"], start=1):
        started = time.monotonic()
        project_id = f"a8-{index:02d}-{item['video_id'][-6:]}"
        run_root = runs_root / project_id
        engine.start_pipeline(
            project_id,
            product_id=product_id,
            source_material_id=item["material_id"],
            source_url=item["source_url"],
            db_path=db_path,
            run_root=run_root,
            mock=mock,
        )
        first_stop = engine.run_until_blocked(project_id, db_path=db_path, run_root=run_root, mock=mock)
        script_gate_passes = 0
        hero_gate_passes = 0
        risks: list[str] = []
        if first_stop.stage != "script_gate" or first_stop.status != "awaiting_human":
            risks.append(f"BLOCKED expected script_gate, got {first_stop.stage}:{first_stop.status}")
        else:
            script_gate_passes += 1
            engine.approve_gate(project_id, "script_gate", approver="a8", db_path=db_path, run_root=run_root)

        second_stop = engine.run_until_blocked(project_id, db_path=db_path, run_root=run_root, mock=mock)
        if second_stop.stage != "hero_gate" or second_stop.status != "awaiting_human":
            risks.append(f"BLOCKED expected hero_gate, got {second_stop.stage}:{second_stop.status}")
        else:
            hero_gate_passes += 1
            engine.approve_gate(project_id, "hero_gate", approver="a8", db_path=db_path, run_root=run_root)

        done = engine.run_until_blocked(project_id, db_path=db_path, run_root=run_root, mock=mock)
        qa_status = _review_status(run_root, "qa_report")
        render_path = _render_path(run_root)
        risks.extend(_output_risks(project_id, run_root))
        elapsed_s = round(time.monotonic() - started, 3)
        cost = cost_tracker.get_project_cost(project_id, db_path=db_path)["total_cost_cny"]
        results.append(
            VideoResult(
                project_id=project_id,
                material_id=item["material_id"],
                status=done.status,
                script_gate_passes=script_gate_passes,
                hero_gate_passes=hero_gate_passes,
                final_qa_status=qa_status,
                business_status=business_status,
                cost_cny=round(float(cost), 4),
                elapsed_s=elapsed_s,
                render_path=render_path,
                risks=risks,
            )
        )

    report = {
        "mode": "mock" if mock else "real",
        "status": "PASS" if all(result.qualified for result in results) and len(results) == count else "BLOCKED",
        "readiness": readiness,
        "results": results,
        "qualified_count": sum(1 for result in results if result.qualified),
        "total_count": count,
        "pricing": _pricing_config(),
        "media_concurrency": _media_concurrency(),
    }
    write_report(report_path, report)
    return report


def real_readiness(env: dict[str, str] | None = None) -> dict[str, Any]:
    selected_env = env or os.environ
    missing = [name for name in REQUIRED_REAL_ENV if not selected_env.get(name)]
    warnings: list[str] = []
    pricing = _pricing_config()
    unset_pricing = [name for name, value in pricing.items() if value is None]
    if unset_pricing:
        warnings.append(f"pricing not calibrated: {', '.join(unset_pricing)}")
    warnings.append("real provider adapters are smoke stubs until actual Doubao/SeedDance API calls are wired")
    return {
        "status": "blocked" if missing else "ready_with_warnings",
        "missing": missing,
        "warnings": warnings,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    results: list[VideoResult] = list(report.get("results") or [])
    lines = [
        "# A8 10 Videos Cutover Report",
        "",
        f"- mode: `{report.get('mode')}`",
        f"- status: `{report.get('status')}`",
        f"- qualified: `{report.get('qualified_count')}/{report.get('total_count')}`",
        f"- media_concurrency: `{report.get('media_concurrency')}`",
        "",
        "## Real Readiness",
        "",
        f"- readiness: `{(report.get('readiness') or {}).get('status')}`",
        f"- missing_env: `{', '.join((report.get('readiness') or {}).get('missing') or []) or 'none'}`",
        f"- warnings: `{'; '.join((report.get('readiness') or {}).get('warnings') or []) or 'none'}`",
        "",
        "## Pricing",
        "",
    ]
    for name, value in (report.get("pricing") or {}).items():
        lines.append(f"- `{name}`: `{value}`")
    lines.extend(
        [
            "",
            "## Results",
            "",
            "| # | project_id | material_id | qualified | final_qa | business | cost_cny | elapsed_s | risks |",
            "|---|------------|-------------|-----------|----------|----------|----------|-----------|-------|",
        ]
    )
    for index, result in enumerate(results, start=1):
        risks = "<br>".join(result.risks) if result.risks else "none"
        lines.append(
            "| {index} | `{project}` | `{material}` | {qualified} | {qa} | {business} | {cost:.4f} | {elapsed:.3f} | {risks} |".format(
                index=index,
                project=result.project_id,
                material=result.material_id,
                qualified="yes" if result.qualified else "no",
                qa=result.final_qa_status,
                business=result.business_status,
                cost=result.cost_cny,
                elapsed=result.elapsed_s,
                risks=risks,
            )
        )
    lines.extend(
        [
            "",
            "## Cutover Decision",
            "",
            "- `real 10/10 PASS`: old system may be switched to read-only backup.",
            "- `mock 10/10 PASS`: internal chain is healthy, but cutover is not approved.",
            "- `<10/10` or any BLOCKED item: old system remains online; defects feed the next round.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _review_status(run_root: Path, artifact_name: str) -> str:
    path = run_root / "artifacts" / f"{artifact_name}.json"
    if not path.exists():
        return "MISSING"
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    return str(payload.get("status") or "UNKNOWN")


def _render_path(run_root: Path) -> str:
    path = run_root / "artifacts" / "render_report.json"
    if not path.exists():
        return ""
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    return str(payload.get("output_path") or "")


def _output_risks(project_id: str, run_root: Path) -> list[str]:
    risks: list[str] = []
    analysis = checkpoint.resolve_artifact(project_id, "analysis_report", run_root=run_root)
    if analysis is None:
        risks.append("BLOCKED missing analysis_report")
    else:
        import json

        payload = json.loads(analysis.read_text(encoding="utf-8"))
        if not payload.get("material_meta_ref"):
            risks.append("BLOCKED missing material_meta_ref")
    for artifact_name in ("script_copy", "shot_plan", "asset_manifest", "render_report", "qa_report", "publish_archive"):
        if checkpoint.resolve_artifact(project_id, artifact_name, run_root=run_root) is None:
            risks.append(f"BLOCKED missing {artifact_name}")
    return risks


def _pricing_config() -> dict[str, Any]:
    config_path = ROOT / "config" / "orchestrator.yaml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return dict(payload.get("pricing") or {})


def _media_concurrency() -> int:
    config_path = ROOT / "config" / "orchestrator.yaml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return int((payload.get("runtime") or {}).get("media_concurrency") or 1)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run A8 10-video cutover validation.")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--product-id", default="便携恒温杯")
    parser.add_argument("--real", action="store_true", help="Require real provider readiness instead of mock mode.")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--runs-root", type=Path)
    parser.add_argument("--material-root", type=Path)
    parser.add_argument("--links-file", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    links = None
    if args.links_file:
        links = [line.strip() for line in args.links_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = run_a8_batch(
        count=args.count,
        product_id=args.product_id,
        mock=not args.real,
        links=links,
        db_path=args.db_path,
        runs_root=args.runs_root,
        material_root=args.material_root,
        report_path=args.report_path,
    )
    print(f"A8 report written: {args.report_path}")
    print(f"status={report['status']} qualified={report['qualified_count']}/{report['total_count']}")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
