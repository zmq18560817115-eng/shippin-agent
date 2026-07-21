from fastapi.testclient import TestClient

from orchestrator import api as api_module
from orchestrator import queue


def test_delivery_download_is_recorded_and_listed(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "delivery.db"
    archive_path = tmp_path / "delivery.zip"
    archive_path.write_bytes(b"PK\x03\x04delivery-test")
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.delenv("VAF_AUTH_ENABLED", raising=False)
    monkeypatch.setattr(api_module, "_build_delivery_zip", lambda project_id: archive_path)
    queue.init_db(db_path)
    queue.ensure_project("delivery-test", product_id="便携恒温杯", db_path=db_path)

    with TestClient(api_module.app) as client:
        response = client.get("/api/v2/download/delivery-test")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"

        history = client.get("/api/v2/delivery/downloads")
        assert history.status_code == 200
        items = history.json()["items"]
        assert len(items) == 1
        assert items[0]["project_id"] == "delivery-test"
        assert items[0]["event_type"] == "delivery.downloaded"
        assert items[0]["meta"]["filename"] == "delivery.zip"
        assert items[0]["meta"]["username"] == "local-operator"
