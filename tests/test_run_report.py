from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator import cost_tracker, engine, queue
from orchestrator.api import app


def test_run_report_summarizes_tasks_and_redacts_provider_meta(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    run_root = tmp_path / "runs" / "report-demo"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))
    queue.init_db(db_path)
    engine.start_pipeline("report-demo", product_id="便携恒温杯", db_path=db_path, run_root=run_root, mock=True)
    engine.run_until_blocked("report-demo", db_path=db_path, run_root=run_root, mock=True)
    cost_tracker.reconcile(
        project_id="report-demo",
        agent="analysis",
        tool="doubao_analyze",
        cost_cny=0,
        model="demo-model",
        meta={"request_id": "request-1", "api_key": "must-not-leak"},
        db_path=db_path,
    )

    with TestClient(app) as client:
        response = client.get("/api/v2/reports/report-demo")
    assert response.status_code == 200
    report = response.json()
    assert report["product_id"] == "便携恒温杯"
    assert report["tasks"]
    provider = next(item for item in report["providers"] if item["meta"].get("request_id") == "request-1")
    assert provider["meta"]["model"] == "demo-model"
    assert provider["meta"]["api_key"] == "[REDACTED]"
    assert "must-not-leak" not in response.text
