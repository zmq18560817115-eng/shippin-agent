from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator.api import app


def test_product_library_api_feeds_asset_stage(tmp_path: Path, monkeypatch) -> None:
    root, white_hero = _sample_product_root(tmp_path)
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "agentflow.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("VAF_PRODUCT_LIBRARY_SOURCES", str(root))
    monkeypatch.setenv("VAF_PRODUCT_LIBRARY_INDEX", str(tmp_path / "product_library_index.json"))

    with TestClient(app) as client:
        refreshed = client.post("/api/v2/product-library/refresh", json={})
        assert refreshed.status_code == 200
        product = refreshed.json()["products"][0]
        assert product["ready"] is True
        assert product["seedance_source"] == white_hero.as_posix()

        products = client.get("/api/v2/products")
        assert products.status_code == 200
        option = products.json()["items"][0]
        assert option["id"] == "便携恒温杯"
        assert option["ready"] is True
        assert option["seedance_source"] == white_hero.as_posix()

        started = client.post(
            "/api/v2/pipeline/run",
            json={"project_id": "ref-product-library", "product_id": "便携恒温杯"},
        )
        assert started.status_code == 200
        assert started.json()["engine"]["stage"] == "script_gate"

        approved = client.post(
            "/api/v2/gates/approve",
            json={"project_id": "ref-product-library", "stage": "script_gate", "approver": "qa"},
        )
        assert approved.status_code == 200
        assert approved.json()["engine"]["stage"] == "hero_gate"

        manifest = client.get("/api/v2/artifacts/ref-product-library/asset_manifest")
        assert manifest.status_code == 200
        payload = manifest.json()
        assert payload["seedance_source"] == white_hero.as_posix()
        assert all(frame["source_refs"] == [white_hero.as_posix()] for frame in payload["hero_frames"])


def _sample_product_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "产品资料"
    root.mkdir()
    (root / "便携恒温杯.md").write_text("# 便携恒温杯\n", encoding="utf-8")
    product_dir = root / "便携恒温杯" / "listing-0602-nw"
    main_dir = product_dir / "主图"
    scene_dir = product_dir / "产品场景使用图"
    main_dir.mkdir(parents=True)
    scene_dir.mkdir(parents=True)
    white_hero = main_dir / "白底主图.png"
    white_hero.write_bytes(b"png")
    (main_dir / "倒出口参考.png").write_bytes(b"png")
    (scene_dir / "场景图1.jpg").write_bytes(b"jpg")
    return root, white_hero
