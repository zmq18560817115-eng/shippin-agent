from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator import engine, queue
from orchestrator.api import app
from tools.llm.doubao_shotplan import ensure_shot_locks


def test_script_gate_blocks_creatively_repeated_script(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "script-quality.db"
    runs_root = tmp_path / "runs"
    run_root = runs_root / "script-quality"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    engine.start_pipeline("script-quality", product_id="便携恒温杯", db_path=db_path, run_root=run_root, mock=True)
    engine.run_until_blocked("script-quality", db_path=db_path, run_root=run_root, mock=True)

    with TestClient(app) as client:
        script = client.get("/api/v2/artifacts/script-quality/script_copy").json()
        for section in script["sections"]:
            section["story_beat_zh"] = "重复剧情推进"
        assert client.put("/api/v2/artifacts/script-quality/script_copy", json=script).status_code == 200
        response = client.post(
            "/api/v2/gates/approve",
            json={"project_id": "script-quality", "gate": "script_gate", "approver": "test", "mock": True},
        )

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "脚本创意质量未通过"
    assert "五段剧情推进不能重复" in response.json()["detail"]["issues"]


def test_hero_gate_repairs_an_older_incomplete_storyboard_prompt(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    runs_root = tmp_path / "runs"
    run_root = runs_root / "preflight-demo"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    engine.start_pipeline("preflight-demo", product_id="便携恒温杯", db_path=db_path, run_root=run_root, mock=True)
    engine.run_until_blocked("preflight-demo", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("preflight-demo", "script_gate", approver="test", db_path=db_path, run_root=run_root)
    engine.run_until_blocked("preflight-demo", db_path=db_path, run_root=run_root, mock=True)

    with TestClient(app) as client:
        plan = client.get("/api/v2/artifacts/preflight-demo/shot_plan").json()
        plan["shots"][0]["seedance_prompt"] = "Product appearance must match the white-background hero reference."
        plan["shots"][0]["visual_prompt"] = plan["shots"][0]["seedance_prompt"]
        for shot in plan["shots"][3:5]:
            shot["seedance_prompt"] = (
                "Continuity lock: same location. Product identity lock: product appearance must match the "
                "white-background hero reference. The warming cup and baby bottle are separate products. "
                "Never insert the bottle into the cup."
            )
        assert client.put("/api/v2/artifacts/preflight-demo/shot_plan", json=plan).status_code == 200
        response = client.post(
            "/api/v2/gates/approve",
            json={"project_id": "preflight-demo", "stage": "hero_gate", "approver": "test", "mock": True},
        )

    assert response.status_code == 200, response.text
    with TestClient(app) as client:
        repaired = client.get("/api/v2/artifacts/preflight-demo/shot_plan").json()
    prompt = repaired["shots"][0]["seedance_prompt"].casefold()
    assert "continuity lock:" in prompt
    assert "fully unlit" in prompt
    for shot in repaired["shots"][3:5]:
        temperature_prompt = shot["seedance_prompt"].casefold()
        assert "temperature proof contract:" in temperature_prompt
        assert "fahrenheit" in temperature_prompt
        assert "never show celsius" in temperature_prompt


def test_hero_gate_blocks_corrupt_temperature_and_mismatched_pour(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    runs_root = tmp_path / "runs"
    run_root = runs_root / "preflight-temperature"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    engine.start_pipeline("preflight-temperature", product_id="便携恒温杯", db_path=db_path, run_root=run_root, mock=True)
    engine.run_until_blocked("preflight-temperature", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("preflight-temperature", "script_gate", approver="test", db_path=db_path, run_root=run_root)
    engine.run_until_blocked("preflight-temperature", db_path=db_path, run_root=run_root, mock=True)

    with TestClient(app) as client:
        plan = client.get("/api/v2/artifacts/preflight-temperature/shot_plan").json()
        plan["shots"][3]["seedance_prompt"] += " Display reads 98掳F."
        plan["shots"][3]["visual"] = "Place the cup in a travel bag."
        plan["shots"][3]["visual_prompt"] = plan["shots"][3]["visual"]
        assert client.put("/api/v2/artifacts/preflight-temperature/shot_plan", json=plan).status_code == 200
        response = client.post(
            "/api/v2/gates/approve",
            json={"project_id": "preflight-temperature", "stage": "hero_gate", "approver": "test", "mock": True},
        )

    assert response.status_code == 409
    missing = response.json()["detail"]["errors"][0]["missing"]
    assert "98°F 温标文本编码" in missing
    assert "第4镜倒液动作一致性" in missing


def test_non_temperature_shots_use_a_hidden_display_contract(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    runs_root = tmp_path / "runs"
    run_root = runs_root / "preflight-hidden-display"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    engine.start_pipeline("preflight-hidden-display", product_id="便携恒温杯", db_path=db_path, run_root=run_root, mock=True)
    engine.run_until_blocked("preflight-hidden-display", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("preflight-hidden-display", "script_gate", approver="test", db_path=db_path, run_root=run_root)
    engine.run_until_blocked("preflight-hidden-display", db_path=db_path, run_root=run_root, mock=True)

    with TestClient(app) as client:
        plan = client.get("/api/v2/artifacts/preflight-hidden-display/shot_plan").json()
        response = client.post(
            "/api/v2/gates/approve",
            json={"project_id": "preflight-hidden-display", "stage": "hero_gate", "approver": "test", "mock": True},
        )

    assert response.status_code == 200
    first_prompt = plan["shots"][0]["seedance_prompt"].casefold()
    assert "never celsius" in first_prompt


def test_saving_an_older_locked_prompt_adds_the_current_display_contract() -> None:
    plan = {
        "shots": [
            {
                "number": 1,
                "seedance_prompt": "Product appearance must match the approved white-background hero reference exactly.",
            }
        ]
    }

    updated = ensure_shot_locks(plan)

    prompt = updated["shots"][0]["seedance_prompt"].casefold()
    assert "product identity lock:" in prompt
    assert "fully unlit" in prompt
    assert "do not render any digits" in prompt
