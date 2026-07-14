from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator import engine, queue
from orchestrator.api import app


def test_agent_map_and_independent_research_strategy_breakdown(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    runs_root = tmp_path / "runs"
    run_root = runs_root / "agent-map-demo"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    engine.start_pipeline(
        "agent-map-demo",
        product_id="便携恒温杯",
        source_text="Late-night caregiver transcript supplied by collector.",
        db_path=db_path,
        run_root=run_root,
        mock=True,
    )
    engine.run_until_blocked("agent-map-demo", db_path=db_path, run_root=run_root, mock=True)

    analysis = (run_root / "artifacts" / "analysis_report.json").read_text(encoding="utf-8")
    assert "Late-night caregiver transcript supplied by collector." in analysis
    assert (run_root / "artifacts" / "research_brief.json").is_file()
    assert (run_root / "artifacts" / "strategy_brief.json").is_file()
    assert (run_root / "artifacts" / "script_breakdown.json").is_file()

    with TestClient(app) as client:
        capability_map = client.get("/api/v2/agents")
        research = client.post(
            "/api/v2/agents/run",
            json={
                "project_id": "agent-map-demo",
                "action": "research",
                "source_text": "A short competitor transcript used only for structural research.",
                "mock": True,
            },
        )
        strategy = client.post(
            "/api/v2/agents/run",
            json={"project_id": "agent-map-demo", "action": "strategy", "mock": True},
        )
        breakdown = client.post(
            "/api/v2/agents/run",
            json={"project_id": "agent-map-demo", "action": "script_breakdown", "mock": True},
        )

    assert capability_map.status_code == 200
    assert capability_map.json()["summary"] == {"total": 9, "deployed": 6, "partial": 3, "missing": 0}
    assert [
        item["independent_action"]
        for item in capability_map.json()["agents"]
        if item["independent_action"]
    ] == ["research", "strategy", "script_breakdown"]
    assert research.status_code == 200
    assert research.json()["artifact_name"] == "research_brief"
    assert strategy.status_code == 200
    assert "98°F" in strategy.json()["artifact"]["product_guardrails"]
    assert breakdown.status_code == 200
    assert len(breakdown.json()["artifact"]["beats"]) == 5
    assert (run_root / "artifacts" / "research_brief.json").is_file()
    assert (run_root / "artifacts" / "strategy_brief.json").is_file()
    assert (run_root / "artifacts" / "script_breakdown.json").is_file()


def test_strategy_requires_research_artifact(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    engine.start_pipeline(
        "missing-research",
        product_id="便携恒温杯",
        db_path=db_path,
        run_root=runs_root / "missing-research",
        mock=True,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={"project_id": "missing-research", "action": "strategy", "mock": True},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "research_brief not found"
