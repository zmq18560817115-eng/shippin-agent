from __future__ import annotations

from pathlib import Path

from scripts.accept.run_a8_10videos import real_readiness, run_a8_batch


def test_a8_mock_batch_writes_10_video_report(tmp_path: Path) -> None:
    report_path = tmp_path / "report_10videos.md"
    report = run_a8_batch(
        count=10,
        mock=True,
        db_path=tmp_path / "agentflow.db",
        runs_root=tmp_path / "runs",
        material_root=tmp_path / "materials",
        report_path=report_path,
    )

    assert report["status"] == "PASS"
    assert report["qualified_count"] == 10
    assert report["total_count"] == 10
    assert report_path.is_file()
    text = report_path.read_text(encoding="utf-8")
    assert "A8 10 Videos Cutover Report" in text
    assert "- qualified: `10/10`" in text
    risks_text = "\n".join(risk for result in report["results"] for risk in result.risks)
    assert "material_meta_ref" not in risks_text


def test_a8_real_readiness_blocks_without_provider_keys() -> None:
    readiness = real_readiness(env={})

    assert readiness["status"] == "blocked"
    assert "DOUBAO_API_KEY" in readiness["missing"]
    assert "SEEDANCE_API_KEY" in readiness["missing"]
