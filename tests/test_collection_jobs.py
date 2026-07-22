from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator import api, queue
from orchestrator.api import app
from tools.base_tool import ToolResult


def test_collection_job_persists_progress_contract(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    job = queue.create_collection_job(
        target_type="keyword",
        provider="browser_search",
        target="portable bottle warmer",
        requested_count=30,
        product_id="便携恒温杯",
        mock=True,
        db_path=db_path,
    )

    assert job["status"] == "queued"
    assert job["provider"] == "browser_search"
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


def test_collection_item_deduplicates_tiktok_video_id_across_url_variants(tmp_path: Path) -> None:
    db_path = tmp_path / "collection-video-id.db"
    job = queue.create_collection_job(
        target_type="keyword",
        provider="auto",
        target="bottle warmer",
        product_id="便携恒温杯",
        requested_count=1,
        mock=False,
        db_path=db_path,
    )
    queue.upsert_collection_item(
        job["id"],
        source_url="https://www.tiktok.com/@first-name/video/7654321?lang=en",
        item={"video_id": "7654321", "title": "Bottle warmer"},
        relevance_score=0.9,
        status="ready",
        db_path=db_path,
    )

    assert queue.collection_url_exists(
        "https://www.tiktok.com/@canonical-name/video/7654321",
        exclude_job_id=None,
        db_path=db_path,
    ) is True
    assert queue.collection_url_exists(
        "https://www.tiktok.com/@canonical-name/video/9999999",
        exclude_job_id=None,
        db_path=db_path,
    ) is False


def test_collection_job_api_create_list_and_cancel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "agentflow.db"))
    monkeypatch.setenv("VAF_COLLECTION_WORKER_ENABLED", "false")

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
    monkeypatch.setenv("VAF_COLLECTION_WORKER_ENABLED", "false")

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/collect/jobs",
            json={"target_type": "keyword", "target": "", "product_id": "便携恒温杯"},
        )

    assert response.status_code == 422
    assert "必须填写目标" in response.json()["detail"]


def test_collection_job_lease_is_exclusive_and_expired_work_recovers(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    job = queue.create_collection_job(
        target_type="keyword",
        provider="auto",
        target="heated cup",
        requested_count=3,
        product_id="便携恒温杯",
        mock=True,
        db_path=db_path,
    )

    claimed = queue.claim_collection_job("worker-a", lease_seconds=30, db_path=db_path)
    assert claimed is not None
    assert claimed["status"] == "running"
    assert claimed["attempt"] == 1
    assert queue.claim_collection_job("worker-b", db_path=db_path) is None

    with queue.get_conn(db_path) as conn:
        conn.execute(
            "UPDATE collection_jobs SET lease_expires_at = '2000-01-01T00:00:00.000Z' WHERE id = ?",
            (job["id"],),
        )
    assert queue.recover_expired_collection_jobs(db_path=db_path) == 1
    recovered = queue.claim_collection_job("worker-b", db_path=db_path)
    assert recovered is not None
    assert recovered["id"] == job["id"]
    assert recovered["attempt"] == 2


def test_collection_job_failure_retries_then_stops(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    job = queue.create_collection_job(
        target_type="keyword",
        provider="auto",
        target="heated cup",
        requested_count=2,
        product_id="便携恒温杯",
        mock=True,
        db_path=db_path,
    )

    first = queue.claim_collection_job("worker", db_path=db_path)
    assert first is not None
    retry = queue.fail_collection_job(
        job["id"], "worker", "temporary block", retryable=True, retry_after_seconds=1, db_path=db_path
    )
    assert retry["status"] == "queued"
    assert retry["next_attempt_at"]

    with queue.get_conn(db_path) as conn:
        conn.execute(
            "UPDATE collection_jobs SET next_attempt_at = '2000-01-01T00:00:00.000Z', max_attempts = 2 WHERE id = ?",
            (job["id"],),
        )
    second = queue.claim_collection_job("worker", db_path=db_path)
    assert second is not None
    stopped = queue.fail_collection_job(job["id"], "worker", "still blocked", retryable=True, db_path=db_path)
    assert stopped["status"] == "failed"
    assert stopped["next_attempt_at"] is None


def test_background_worker_writes_job_progress(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    job = queue.create_collection_job(
        target_type="keyword",
        provider="auto",
        target="heated cup",
        requested_count=2,
        product_id="便携恒温杯",
        mock=True,
        db_path=db_path,
    )
    monkeypatch.setattr(
        api.tool_registry,
        "execute_tool",
        lambda *args, **kwargs: ToolResult.success(
            {
                "provider": "mock",
                "items": [
                    {"url": "https://www.tiktok.com/@demo/video/3", "caption": "unrelated dance clip"},
                    {"url": "https://www.tiktok.com/@demo/video/1", "caption": "heated cup bottle warmer"},
                    {"url": "https://www.tiktok.com/@demo/video/2", "caption": "portable milk warmer review"},
                ],
            }
        ),
    )
    monkeypatch.setattr(
        api,
        "collect_tiktok_and_run",
        lambda request: {
            "ok": True,
            "material": {"material_id": request.url.rsplit("/", 1)[-1]},
            "project_id": f"project-{request.url.rsplit('/', 1)[-1]}",
        },
    )

    result = api._run_collection_job_once("test-worker")

    assert result is not None and result["ok"] is True
    completed = queue.get_collection_job(job["id"], db_path=db_path)
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert completed["progress"]["discovered"] == 3
    assert completed["progress"]["relevant"] == 2
    assert completed["progress"]["downloaded"] == 2
    assert completed["progress"]["analyzed"] == 2

    items = queue.list_collection_items(job["id"], db_path=db_path)
    assert [item["status"] for item in items].count("ready") == 2
    assert [item["status"] for item in items].count("filtered") == 1


def test_collection_worker_replenishes_and_deduplicates_across_jobs(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    prior = queue.create_collection_job(
        target_type="keyword",
        provider="auto",
        target="heated cup",
        requested_count=1,
        product_id="便携恒温杯",
        mock=True,
        db_path=db_path,
    )
    duplicate_url = "https://www.tiktok.com/@demo/video/100"
    queue.upsert_collection_item(
        prior["id"],
        source_url=duplicate_url,
        item={"url": duplicate_url, "caption": "heated cup demo"},
        relevance_score=1.0,
        status="ready",
        db_path=db_path,
    )
    queue.cancel_collection_job(prior["id"], db_path=db_path)

    job = queue.create_collection_job(
        target_type="keyword",
        provider="auto",
        target="heated cup",
        requested_count=2,
        product_id="便携恒温杯",
        mock=True,
        db_path=db_path,
    )
    rounds = [
        [
            {"url": duplicate_url, "caption": "heated cup demo"},
            {"url": "https://www.tiktok.com/@demo/video/101", "caption": "makeup tutorial"},
            {"url": "https://www.tiktok.com/@demo/video/102", "caption": "portable bottle warmer for travel"},
        ],
        [
            {"url": "https://www.tiktok.com/@demo/video/103", "caption": "formula milk warmer night feeding"},
        ],
    ]

    def discover(*args, **kwargs):
        return ToolResult.success({"provider": "mock", "items": rounds.pop(0) if rounds else []})

    processed: list[str] = []
    monkeypatch.setattr(api.tool_registry, "execute_tool", discover)

    def intake(request):
        processed.append(request.url)
        suffix = request.url.rsplit("/", 1)[-1]
        return {"material": {"material_id": suffix}, "project_id": f"project-{suffix}"}

    monkeypatch.setattr(api, "collect_tiktok_and_run", intake)

    result = api._run_collection_job_once("test-worker")

    assert result is not None and result["ok"] is True
    assert processed == [
        "https://www.tiktok.com/@demo/video/102",
        "https://www.tiktok.com/@demo/video/103",
    ]
    completed = queue.get_collection_job(job["id"], db_path=db_path)
    assert completed is not None
    assert completed["status"] == "succeeded"
    assert completed["progress"] == {
        "requested": 2,
        "discovered": 4,
        "relevant": 2,
        "downloaded": 2,
        "analyzed": 2,
        "failed": 0,
    }
    items = queue.list_collection_items(job["id"], db_path=db_path)
    reasons = {item["source_url"]: item["error_message"] for item in items if item["status"] == "filtered"}
    assert duplicate_url in reasons
    assert "101" in next(url for url in reasons if url.endswith("101"))
