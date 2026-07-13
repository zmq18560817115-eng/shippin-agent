from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agents import worker
from orchestrator import queue
from orchestrator.api import app
from scripts.verify_deploy_repo import verify
from tools.collect import manual_import


SAMPLE_LINKS = [
    "https://www.tiktok.com/@demo/video/7000000000000000001",
    "https://www.tiktok.com/@demo/video/7000000000000000002",
    "https://www.tiktok.com/@demo/video/7000000000000000003",
    "https://www.tiktok.com/@demo/video/7000000000000000004",
    "https://www.tiktok.com/@demo/video/7000000000000000005",
]


def test_a7_manual_import_five_links_can_start_pipelines(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "agentflow.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("VAF_MATERIAL_LIBRARY_ROOT", str(tmp_path / "materials"))

    with TestClient(app) as client:
        imported = client.post(
            "/api/v2/collect/manual",
            json={
                "links_text": "\n".join(SAMPLE_LINKS),
                "product_id": "便携恒温杯",
                "source_keyword": "night_feed_manual",
            },
        )
        assert imported.status_code == 200
        assert imported.json()["imported_count"] == 5

        library = client.get("/api/v2/collect/library?limit=10")
        assert library.status_code == 200
        items = library.json()["items"]
        assert len(items) == 5
        assert all(item["material_meta"]["asset_intake"]["approval_status"] == "needs_review" for item in items)

        for index, item in enumerate(items, start=1):
            response = client.post(
                "/api/v2/pipeline/run",
                json={
                    "project_id": f"ref-a7-{index}",
                    "product_id": "便携恒温杯",
                    "source_material_id": item["material_id"],
                },
            )
            payload = response.json()
            assert response.status_code == 200
            assert payload["engine"]["stage"] == "script_gate"
            assert payload["engine"]["status"] == "awaiting_human"
            assert payload["project"]["source_material_id"] == item["material_id"]


def test_a7_collector_worker_imports_manual_links(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    material_root = tmp_path / "materials"
    monkeypatch.setenv("VAF_MATERIAL_LIBRARY_ROOT", str(material_root))
    queue.init_db(db_path=db_path)
    task_id = queue.enqueue_task(
        project_id="collector-a7",
        stage="manual_import",
        agent="collector",
        task_type="manual_import",
        payload={
            "urls": SAMPLE_LINKS[:2],
            "product_id": "便携恒温杯",
            "source_keyword": "worker_manual",
            "library_root": material_root.as_posix(),
        },
        db_path=db_path,
    )

    worker.main(["--db-path", str(db_path), "--agents", "collector", "--once"])

    task = queue.get_task(task_id, db_path=db_path)
    assert task.status == "succeeded"
    assert task.result_json["imported_count"] == 2
    index = manual_import.load_library_index(material_root)
    assert len(index["items"]) == 2


def test_a7_deploy_repo_verification_passes() -> None:
    assert verify() == []
