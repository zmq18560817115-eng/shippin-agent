from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator import api, engine, queue
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
    assert capability_map.json()["summary"] == {"total": 11, "deployed": 7, "partial": 4, "missing": 0}
    schemas = capability_map.json()["input_schemas"]
    assert {field["name"] for field in schemas["collector"]} == {"target_type", "target", "limit", "persist"}
    assert {field["name"] for field in schemas["script"]} == {"product_id", "prompt"}
    assert {field["name"] for field in schemas["script_breakdown"]} == {"product_id", "source_text"}
    assert all(any(field.get("required") for field in fields) for action, fields in schemas.items() if action != "collector")
    assert [
        item["independent_action"]
        for item in capability_map.json()["agents"]
        if item["independent_action"]
    ] == ["orchestrator", "collector", "analysis", "research", "strategy", "script,script_breakdown", "storyboard", "asset", "production", "review", "feedback"]
    assert research.status_code == 200
    assert research.json()["artifact_name"] == "research_brief"
    assert strategy.status_code == 200
    assert strategy.json()["artifact"]["product_guardrails"]["display"]["approved_value"] == "98°F"
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


def test_standalone_strategy_and_breakdown_cold_start_are_isolated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "standalone.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))

    with TestClient(app) as client:
        strategy = client.post(
            "/api/v2/agents/run",
            json={
                "action": "strategy",
                "product_id": "便携恒温杯",
                "source_text": "面向夜间喂养照护者，突出准备流程更从容。",
                "mock": True,
            },
        )
        breakdown = client.post(
            "/api/v2/agents/run",
            json={
                "action": "script_breakdown",
                "product_id": "便携恒温杯",
                "source_text": "为便携恒温杯写一条夜间喂养的 30 秒短视频脚本。",
                "mock": True,
            },
        )
        visible = client.get("/api/v2/pipeline")
        all_projects = client.get("/api/v2/pipeline?include_standalone=true")
        strategy_download = client.get(strategy.json()["download_url"])

    assert strategy.status_code == 200, strategy.text
    assert breakdown.status_code == 200, breakdown.text
    assert strategy.json()["project_id"].startswith("scratch-")
    assert breakdown.json()["project_id"].startswith("scratch-")
    assert strategy.json()["artifact_name"] == "strategy_brief"
    assert len(breakdown.json()["artifact"]["beats"]) >= 1
    assert breakdown.json()["artifact"]["beats"][0]["source_quote"].startswith("为便携恒温杯写一条")
    assert strategy_download.status_code == 200
    assert all(not item["standalone"] for item in visible.json()["items"])
    assert any(item["standalone"] for item in all_projects.json()["items"])


def test_standalone_analysis_review_and_feedback_are_downloadable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "standalone-tools.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("VAF_FEEDBACK_ROOT", str(tmp_path / "feedback"))

    with TestClient(app) as client:
        analysis = client.post(
            "/api/v2/agents/run",
            json={"action": "analysis", "source_text": "夜间准备奶液时等待太久，照护者需要更从容的流程。", "mock": True},
        )
        review = client.post(
            "/api/v2/agents/run",
            json={"action": "review", "source_text": "为便携恒温杯写一条安全的夜间喂养短视频脚本。", "mock": True},
        )
        feedback = client.post(
            "/api/v2/agents/run",
            json={
                "action": "feedback",
                "source_text": "减少空镜头，明确展示独立奶瓶与正确倒液方向。",
                "creative_style": "真实生活方式广告",
                "target_audience": "夜间喂养的新手父母",
                "creative_freedom": "exploratory",
                "mock": True,
            },
        )

        analysis_download = client.get(analysis.json()["download_url"])
        review_download = client.get(review.json()["download_url"])
        feedback_download = client.get(feedback.json()["download_url"])

    assert analysis.status_code == 200, analysis.text
    assert review.status_code == 200, review.text
    assert feedback.status_code == 200, feedback.text
    assert analysis.json()["artifact_name"] == "analysis_report"
    assert review.json()["artifact_name"] == "review_report"
    assert feedback.json()["artifact_name"] == "feedback_record"
    assert feedback.json()["artifact"]["insights"]["priority"] == "medium"
    assert "product_accuracy" in feedback.json()["artifact"]["insights"]["categories"]
    assert feedback.json()["meta"]["agent_contract"]["identity"]
    assert feedback.json()["meta"]["creative_brief"]["freedom"] == "exploratory"
    assert all(response.status_code == 200 for response in (analysis_download, review_download, feedback_download))


def test_standalone_analysis_tiktok_url_uses_capture_transcript_pipeline(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    material_root = tmp_path / "materials"
    report_path = material_root / "tt_123" / "analysis_report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "version": "2.0",
                "project_id": "material-tt_123",
                "source_link_id": None,
                "material_meta_ref": "tt_123",
                "hook_3s": "地铁门即将关闭",
                "structure": ["钩子", "展开", "结果"],
                "voiceover_text": "真实 ASR 转写内容",
                "pacing": [{"start_s": 0, "end_s": 6, "role": "钩子"}],
                "keyframes": [],
                "shot_breakdown": [],
                "fingerprint": "captured-test",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "url-analysis.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))

    def fake_capture(request):
        assert request.analysis_only is True
        return {
            "ok": True,
            "material": {"material_id": "tt_123", "breakdown_path": report_path.as_posix()},
            "readiness": {"ready": True},
        }

    monkeypatch.setattr(api, "collect_tiktok_and_run", fake_capture)

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={
                "action": "analysis",
                "source_text": "https://www.tiktok.com/@demo/video/123",
                "mock": False,
            },
        )
        download = client.get(response.json()["download_url"])

    assert response.status_code == 200, response.text
    assert response.json()["artifact"]["voiceover_text"] == "真实 ASR 转写内容"
    assert response.json()["artifact"]["project_id"].startswith("scratch-")
    assert response.json()["meta"]["source_mode"] == "tiktok_capture"
    assert download.status_code == 200


def test_standalone_analysis_rejects_unsupported_video_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "unsupported-url.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={"action": "analysis", "source_text": "https://example.com/video/123", "mock": True},
        )

    assert response.status_code == 422
    assert "当前支持 TikTok" in response.json()["detail"]


def test_standalone_research_tiktok_url_uses_captured_transcript(tmp_path: Path, monkeypatch) -> None:
    report_path = tmp_path / "materials" / "tt_456" / "analysis_report.json"
    report_path.parent.mkdir(parents=True)
    transcript = "创作者在机场登机口展示收纳流程，先整理证件，再把随身用品放入侧袋。"
    report_path.write_text(
        json.dumps(
            {
                "version": "2.0",
                "project_id": "material-tt_456",
                "source_link_id": None,
                "material_meta_ref": "tt_456",
                "hook_3s": "登机广播响起",
                "structure": ["钩子", "步骤", "结果"],
                "voiceover_text": transcript,
                "pacing": [{"start_s": 0, "end_s": 6, "role": "钩子"}],
                "keyframes": [],
                "shot_breakdown": [],
                "fingerprint": "research-capture-test",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "url-research.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))

    def fake_capture(request):
        assert request.analysis_only is True
        return {
            "ok": True,
            "material": {"material_id": "tt_456", "breakdown_path": report_path.as_posix()},
            "readiness": {"ready": True},
        }

    monkeypatch.setattr(api, "collect_tiktok_and_run", fake_capture)

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={
                "action": "research",
                "source_text": "https://www.tiktok.com/@demo/video/456",
                "mock": True,
            },
        )

    assert response.status_code == 200, response.text
    artifact = response.json()["artifact"]
    assert transcript in artifact["source_summary"]
    assert "tt_456" in artifact["source_refs"]
    assert response.json()["meta"]["source_mode"] == "tiktok_capture"


def test_standalone_non_pour_production_does_not_leak_action_references(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "standalone-production.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={
                "action": "production",
                "product_id": "便携恒温杯",
                "prompt": "产品闭盖放在床头柜上，不展示倒液动作。",
                "mock": True,
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["meta"]["reference_paths"] == []


def test_standalone_unknown_product_production_uses_prompt_only_identity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "prompt-only-production.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={
                "action": "production",
                "product_id": "折叠雨伞",
                "prompt": "雨天街道上打开一把红色折叠雨伞，镜头缓慢推进。",
                "mock": True,
            },
        )

    assert response.status_code == 200, response.text
    meta = response.json()["meta"]
    assert meta["seedance_source"] == ""
    assert meta["reference_paths"] == []
    artifact = response.json()["artifact"]
    assert artifact["shots"][0]["status"] == "succeeded"


def test_standalone_unknown_product_asset_requires_approved_material(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "unknown-asset.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={
                "action": "asset",
                "product_id": "折叠雨伞",
                "prompt": "生成雨伞产品身份关键帧。",
                "mock": True,
            },
        )

    assert response.status_code == 422
    assert "没有已批准的产品主图" in response.json()["detail"]


def test_orchestrator_and_asset_are_independently_runnable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "standalone-control.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))

    with TestClient(app) as client:
        orchestrator = client.post(
            "/api/v2/agents/run",
            json={
                "action": "orchestrator",
                "product_id": "便携恒温杯",
                "prompt": "规划一条 30 秒恒温杯产品视频生产任务。",
                "creative_style": "电影感叙事",
                "target_audience": "新手父母",
                "creative_freedom": "balanced",
                "mock": True,
            },
        )
        asset = client.post(
            "/api/v2/agents/run",
            json={
                "action": "asset",
                "product_id": "便携恒温杯",
                "prompt": "夜间床头场景中的产品身份关键帧。",
                "mock": True,
            },
        )
        asset_download = client.get(asset.json()["download_url"])

    assert orchestrator.status_code == 200, orchestrator.text
    assert orchestrator.json()["artifact_name"] == "orchestration_plan"
    assert len(orchestrator.json()["artifact"]["route"]) == 6
    assert orchestrator.json()["artifact"]["creative_brief"]["style"] == "电影感叙事"
    assert orchestrator.json()["meta"]["agent_contract"]["identity"]
    assert asset.status_code == 200, asset.text
    assert asset.json()["artifact_name"] == "asset_manifest"
    assert asset.json()["artifact"]["hero_frames"][0]["status"] == "needs_review"
    assert asset.json()["artifact"]["hero_frames"][0]["scene_preview_available"] is False
    assert asset_download.status_code == 200


def test_independent_agent_rejects_unknown_creative_freedom(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "creative-controls.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={
                "action": "script",
                "source_text": "生成一条产品短视频脚本。",
                "creative_freedom": "unlimited",
                "mock": True,
            },
        )

    assert response.status_code == 422
    assert "creative_freedom" in response.json()["detail"]


def test_standalone_script_promotes_to_a_gated_production_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "promotion.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))

    with TestClient(app) as client:
        standalone = client.post(
            "/api/v2/agents/run",
            json={
                "action": "script",
                "product_id": "便携恒温杯",
                "source_text": "为夜间喂养场景制作便携恒温杯的 30 秒产品短视频。",
                "mock": True,
            },
        )
        promoted = client.post(
            "/api/v2/agents/promote",
            json={
                "source_project_id": standalone.json()["project_id"],
                "artifact_name": "script_copy",
                "mock": True,
            },
        )

    assert standalone.status_code == 200, standalone.text
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["project_id"].startswith("ref-")
    assert promoted.json()["project"]["standalone"] is False
    assert promoted.json()["project"]["current_stage"] == "script_gate"
    assert promoted.json()["engine"]["status"] == "awaiting_human"


def test_promoted_script_preserves_standalone_product_identity(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "promotion-product.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))

    with TestClient(app) as client:
        standalone = client.post(
            "/api/v2/agents/run",
            json={
                "action": "script",
                "product_id": "折叠雨伞",
                "source_text": "为通勤人群创作一条雨天使用折叠雨伞的短视频脚本。",
                "mock": True,
            },
        )
        promoted = client.post(
            "/api/v2/agents/promote",
            json={
                "source_project_id": standalone.json()["project_id"],
                "artifact_name": "script_copy",
                "mock": True,
            },
        )

    assert standalone.status_code == 200, standalone.text
    assert standalone.json()["artifact"]["product_id"] == "折叠雨伞"
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["project"]["product_id"] == "折叠雨伞"


def test_independent_content_agents_preserve_distinct_user_intent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "intent-aware.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))
    travel = "便携恒温杯用于高铁旅行，新手照护者携带宝宝出行，投放 TikTok。"
    office = "便携恒温杯用于办公室午休，通勤照护者会议前快速准备，投放 TikTok。"

    with TestClient(app) as client:
        travel_research = client.post(
            "/api/v2/agents/run",
            json={"action": "research", "source_text": travel, "mock": True},
        )
        office_research = client.post(
            "/api/v2/agents/run",
            json={"action": "research", "source_text": office, "mock": True},
        )
        travel_strategy = client.post(
            "/api/v2/agents/run",
            json={"action": "strategy", "source_text": travel, "mock": True},
        )
        office_strategy = client.post(
            "/api/v2/agents/run",
            json={"action": "strategy", "source_text": office, "mock": True},
        )
        travel_script = client.post(
            "/api/v2/agents/run",
            json={"action": "script", "source_text": travel, "mock": True},
        )
        office_script = client.post(
            "/api/v2/agents/run",
            json={"action": "script", "source_text": office, "mock": True},
        )
        travel_storyboard = client.post(
            "/api/v2/agents/run",
            json={"action": "storyboard", "source_text": travel, "mock": True},
        )
        unsafe_review = client.post(
            "/api/v2/agents/run",
            json={"action": "review", "source_text": "恒温杯显示 98°C，再把整个奶瓶放入杯中加热。", "mock": True},
        )

    responses = (
        travel_research,
        office_research,
        travel_strategy,
        office_strategy,
        travel_script,
        office_script,
        travel_storyboard,
        unsafe_review,
    )
    assert all(response.status_code == 200 for response in responses)

    travel_research_text = str(travel_research.json()["artifact"])
    office_research_text = str(office_research.json()["artifact"])
    assert "旅途" in travel_research_text
    assert "工作" in office_research_text
    assert travel_research_text != office_research_text

    travel_strategy_text = str(travel_strategy.json()["artifact"])
    office_strategy_text = str(office_strategy.json()["artifact"])
    assert "旅途" in travel_strategy_text
    assert "办公室" in office_strategy_text
    assert travel_strategy_text != office_strategy_text

    travel_sections = travel_script.json()["artifact"]["sections"]
    office_sections = office_script.json()["artifact"]["sections"]
    assert "高铁" in travel_sections[0]["scene_zh"]
    assert "办公室" in office_sections[0]["scene_zh"]
    assert travel_sections[0]["voiceover_zh"] != office_sections[0]["voiceover_zh"]
    assert travel_script.json()["artifact"]["creative_request"]

    storyboard = travel_storyboard.json()["artifact"]
    assert "高铁" in storyboard["scene_continuity"]
    assert "高铁" in storyboard["shots"][0]["visual"]
    assert len(storyboard["shots"]) == 5

    review = unsafe_review.json()["artifact"]
    assert review["status"] == "BLOCKED"
    assert all(comment.startswith("源稿：") for comment in review["comments"])
    assert any("98°F" in comment for comment in review["comments"])
    assert any("独立物体" in comment for comment in review["comments"])

    for script in (travel_script.json()["artifact"], office_script.json()["artifact"]):
        joined = str(script)
        assert "98°C" not in joined
        assert "独立" in script["sections"][3]["action_zh"]


def test_standalone_script_and_storyboard_support_non_library_product_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "generic-product.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))
    brief = "为城市通勤人群创作折叠雨伞短视频，重点表现进地铁前突然下雨，不虚构材质和防风等级。"

    with TestClient(app) as client:
        script_response = client.post(
            "/api/v2/agents/run",
            json={"action": "script", "product_id": "折叠雨伞", "prompt": brief, "mock": True},
        )
        storyboard_response = client.post(
            "/api/v2/agents/run",
            json={"action": "storyboard", "product_id": "折叠雨伞", "prompt": brief, "mock": True},
        )
        strategy_response = client.post(
            "/api/v2/agents/run",
            json={"action": "strategy", "product_id": "折叠雨伞", "source_text": brief, "mock": True},
        )

    assert script_response.status_code == 200, script_response.text
    assert storyboard_response.status_code == 200, storyboard_response.text
    assert strategy_response.status_code == 200, strategy_response.text
    script = script_response.json()["artifact"]
    storyboard = storyboard_response.json()["artifact"]
    assert script["product_id"] == "折叠雨伞"
    assert "折叠雨伞" in str(script)
    assert "恒温杯" not in str(script)
    assert "奶瓶" not in str(script)
    assert "98°F" not in str(script)
    assert "折叠雨伞" in str(storyboard)
    assert "warming cup" not in str(storyboard).casefold()
    assert "baby bottle" not in str(storyboard).casefold()
    assert "98 degrees fahrenheit" not in str(storyboard).casefold()
    strategy = strategy_response.json()["artifact"]
    assert strategy["product_id"] == "折叠雨伞"
    assert "折叠雨伞" in str(strategy["selling_point_priority"])
    assert "便携机身" not in str(strategy["selling_point_priority"])
    assert "准备步骤清晰" not in str(strategy["selling_point_priority"])


def test_standalone_review_audits_original_text_without_rewriting_script(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "direct-review.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    source = "折叠雨伞是全网第一，保证百分百防风。"

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={"action": "review", "product_id": "折叠雨伞", "source_text": source, "mock": True},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["artifact"]["status"] == "BLOCKED"
    assert payload["artifact"]["input_summary"] == source
    assert any("绝对化" in comment for comment in payload["artifact"]["comments"])
    assert not (runs_root / payload["project_id"] / "artifacts" / "script_copy.json").exists()


def test_generic_review_does_not_apply_warming_cup_temperature_rule(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "generic-review.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={
                "action": "review",
                "product_id": "厨房温度计",
                "source_text": "演示厨房温度计测量烤箱内部达到 98°C。",
                "mock": True,
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["artifact"]["status"] == "PASS"


def test_standalone_breakdown_preserves_original_lines_without_script_rewrite(tmp_path: Path, monkeypatch) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "direct-breakdown.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    source = "雨突然落下。她在地铁入口停住。折叠雨伞从包侧袋取出。三秒撑开后继续赶路。"

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={"action": "script_breakdown", "product_id": "折叠雨伞", "source_text": source, "mock": True},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    beats = payload["artifact"]["beats"]
    assert "".join(beat["source_quote"] for beat in beats) == source
    assert all(beat["voiceover"] == beat["source_quote"] for beat in beats)
    assert all(beat["human_editable"] is True for beat in beats)
    assert not (runs_root / payload["project_id"] / "artifacts" / "script_copy.json").exists()


def test_standalone_content_agents_reject_empty_default_generation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "empty-input.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))

    with TestClient(app) as client:
        responses = {
            action: client.post("/api/v2/agents/run", json={"action": action, "mock": True})
            for action in (
                "analysis", "research", "strategy", "script", "script_breakdown",
                "storyboard", "asset", "production", "review", "feedback",
            )
        }

    assert all(response.status_code == 422 for response in responses.values())
    assert all("不会用默认模板" in response.json()["detail"] for response in responses.values())


def test_real_script_normalizer_fallback_preserves_user_scenario() -> None:
    from tools.llm.doubao_script import _normalize_sections
    from tools.llm.mock_artifacts import mock_script_copy

    fallback = mock_script_copy(
        "fallback-test",
        creative_request="高铁旅行途中，新手照护者携带宝宝出行",
    )["sections"]
    sections = _normalize_sections({}, fallback_sections=fallback)

    assert "高铁" in sections[0]["scene_zh"]
    assert "行程" in sections[0]["voiceover_zh"]
    assert "卧室" not in str(sections)


def test_real_storyboard_normalizer_fallback_preserves_script_scenario() -> None:
    from tools.llm.doubao_shotplan import _normalize_shots
    from tools.llm.mock_artifacts import mock_script_copy, mock_shot_plan

    script = mock_script_copy("storyboard-fallback", creative_request="高铁旅行途中，新手照护者携带宝宝出行")
    fallback = mock_shot_plan("storyboard-fallback", script)
    shots = _normalize_shots(
        {},
        script,
        scene_continuity=fallback["scene_continuity"],
        character_continuity=fallback["character_continuity"],
        fallback_shots=fallback["shots"],
    )

    assert "高铁" in shots[0]["visual"]
    assert "高铁" in shots[2]["visual"]
    assert "卧室" not in " ".join(shot["visual"] for shot in shots)
