from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator import queue
from orchestrator.api import app


def test_collection_job_persists_progress_contract(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    job = queue.create_collection_job(
        target_type="keyword",
        provider="auto",
        target="portable bottle warmer",
        requested_count=30,
        product_id="便携恒温杯",
        mock=True,
        db_path=db_path,
    )

    assert job["status"] == "queued"
    assert job["requested_count"] == 30
    assert job["progress"] == {
        "requested": 30,
        "discovered": 0,
        "relevant": 0,
        "downloaded": 0,
        "analyzed": 0,
        "failed": 0,
    }
    assert queue.list_collection_jobs(status="queued", db_path=db_path)[0]["id"] == job["id"]

    cancelled = queue.cancel_collection_job(job["id"], db_path=db_path)
    assert cancelled is not None
    assert cancelled["status"] == "cancelled"
    assert cancelled["finished_at"]


def test_collection_job_api_create_list_and_cancel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "agentflow.db"))

    with TestClient(app) as client:
        created = client.post(
            "/api/v2/collect/jobs",
            json={
                "target_type": "keyword",
                "provider": "auto",
                "target": "heated cup",
                "requested_count": 25,
                "product_id": "便携恒温杯",
                "mock": True,
            },
        )
        assert created.status_code == 201, created.text
        job = created.json()["job"]

        listed = client.get("/api/v2/collect/jobs", params={"status": "queued"})
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["jobs"]] == [job["id"]]

        detail = client.get(f"/api/v2/collect/jobs/{job['id']}")
        assert detail.status_code == 200
        assert detail.json()["job"]["target"] == "heated cup"

        cancelled = client.post(f"/api/v2/collect/jobs/{job['id']}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["job"]["status"] == "cancelled"


def test_collection_job_api_rejects_missing_target(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "agentflow.db"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/collect/jobs",
            json={"target_type": "keyword", "target": "", "product_id": "便携恒温杯"},
        )

    assert response.status_code == 422
    assert "必须填写目标" in response.json()["detail"]
