from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator.api import app


def test_a6_api_workbench_two_gate_flow_and_polling(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "agentflow.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("VAF_FEEDBACK_ROOT", str(tmp_path / "feedback"))

    with TestClient(app) as client:
        started = client.post(
            "/api/v2/pipeline/run",
            json={
                "project_id": "ref-a6",
                "product_id": "便携恒温杯",
                "link_id": 101,
            },
        )
        assert started.status_code == 200
        started_payload = started.json()
        assert started_payload["engine"]["stage"] == "script_gate"
        assert started_payload["engine"]["status"] == "awaiting_human"
        assert started_payload["project"]["current_gate"] == "script_gate"

        script_response = client.get("/api/v2/artifacts/ref-a6/script_copy")
        assert script_response.status_code == 200
        script_copy = script_response.json()
        script_copy["sections"][0]["voiceover_en"] = "Night feeds should feel calmer."
        saved = client.put("/api/v2/artifacts/ref-a6/script_copy", json=script_copy)
        assert saved.status_code == 200
        assert saved.json()["stale_sections"] == [1]

        script_gate = client.post(
            "/api/v2/gates/approve",
            json={"project_id": "ref-a6", "stage": "script_gate", "approver": "qa"},
        )
        assert script_gate.status_code == 200
        assert script_gate.json()["engine"]["stage"] == "hero_gate"

        manifest = client.get("/api/v2/artifacts/ref-a6/asset_manifest")
        assert manifest.status_code == 200
        assert manifest.json()["hero_frames"]

        regenerated = client.post(
            "/api/v2/hero/regen",
            json={"project_id": "ref-a6", "shot_index": 1},
        )
        assert regenerated.status_code == 200
        assert regenerated.json()["shot_index"] == 1

        hero_gate = client.post(
            "/api/v2/gates/approve",
            json={"project_id": "ref-a6", "stage": "hero_gate", "approver": "qa"},
        )
        assert hero_gate.status_code == 200
        assert hero_gate.json()["engine"]["stage"] == "take_gate"
        assert hero_gate.json()["engine"]["status"] == "awaiting_human"

        takes = client.get("/api/v2/artifacts/ref-a6/take_manifest").json()
        for shot in takes["shots"]:
            take_id = shot["takes"][0]["take_id"]
            reviewed = client.post(
                "/api/v2/takes/review",
                json={"project_id": "ref-a6", "shot_index": shot["number"], "take_id": take_id,
                      "product_identity": True, "no_invented_brand": True, "temperature_display": True,
                      "usage_flow": True, "continuity": True},
            )
            assert reviewed.status_code == 200
            selected = client.post("/api/v2/takes/select", json={"project_id": "ref-a6", "shot_index": shot["number"], "take_id": take_id})
            assert selected.status_code == 200
        take_gate = client.post("/api/v2/gates/approve", json={"project_id": "ref-a6", "stage": "take_gate", "approver": "qa"})
        assert take_gate.status_code == 200
        assert take_gate.json()["engine"]["stage"] == "final_qa"
        assert take_gate.json()["engine"]["status"] == "blocked"
        final_review = client.post(
            "/api/v2/review/final-visual",
            json={"project_id": "ref-a6", "product_identity": True, "no_invented_brand": True,
                  "temperature_display": True, "usage_flow": True, "person_scene_continuity": True},
        )
        assert final_review.status_code == 200
        assert final_review.json()["engine"]["stage"] == "archive"
        assert final_review.json()["engine"]["status"] == "succeeded"

        def poll_pipeline(_: int) -> int:
            with TestClient(app) as polling_client:
                response = polling_client.get("/api/v2/pipeline?limit=50")
                assert response.json()["items"][0]["project_id"] == "ref-a6"
                return response.status_code

        with ThreadPoolExecutor(max_workers=10) as pool:
            assert list(pool.map(poll_pipeline, range(10))) == [200] * 10

        download = client.get("/api/v2/download/ref-a6")
        assert download.status_code == 200
        assert download.content.startswith(b"PK")

        feedback = client.post(
            "/api/v2/feedback",
            json={"project_id": "ref-a6", "text": "Mock delivery approved."},
        )
        assert feedback.status_code == 200
        assert Path(feedback.json()["path"]).is_file()

        root = client.get("/")
        assert root.status_code == 200
        assert "/static/login.js" in root.text


def test_a6_script_gate_rewrite_returns_to_script_gate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "agentflow.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))

    with TestClient(app) as client:
        started = client.post(
            "/api/v2/pipeline/run",
            json={"project_id": "ref-a6-rewrite", "product_id": "便携恒温杯"},
        )
        assert started.status_code == 200
        assert started.json()["engine"]["stage"] == "script_gate"

        rewritten = client.post(
            "/api/v2/gates/rewrite",
            json={
                "project_id": "ref-a6-rewrite",
                "stage": "script_gate",
                "reason": "tighten hook",
            },
        )
        assert rewritten.status_code == 200
        assert rewritten.json()["engine"]["stage"] == "script_gate"
        assert rewritten.json()["engine"]["status"] == "awaiting_human"
