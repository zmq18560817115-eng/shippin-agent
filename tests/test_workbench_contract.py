from pathlib import Path


def test_manual_stage_uses_existing_runtime_mode_control() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    script = Path("web/app.js").read_text(encoding="utf-8")

    assert 'id="runtimeMode"' in html
    assert '$("#runtimeMode").value' in script
    assert '$("#runMode")' not in script


def test_agent_capabilities_are_nested_in_existing_workflow_nodes() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    script = Path("web/app.js").read_text(encoding="utf-8")

    assert 'id="agentMap"' not in html
    assert 'href="#agentMap"' not in html
    assert 'id="researchNode"' in html
    assert 'id="runStrategy"' in html
    assert 'id="runScriptBreakdown"' in html
    assert "runFlowCapability" in script
    assert 'api("/api/v2/agents/run"' in script
    assert "采集并分析" in html
    assert 'api("/api/v2/collect/tiktok/run"' in script
    assert "主动爬取任务" in html
    assert 'api("/api/v2/collect/jobs"' in script
    assert 'id="collectionJobList"' in html
    assert 'id="collectionJobDetail"' in html
    assert "function loadCollectionJobs" in script
    assert 'id="crawlProvider"' in html
    assert 'provider: $("#crawlProvider").value' in script
    assert "生成第一个候选 Take" in script
    assert 'api("/api/v2/takes/select"' in script
    assert 'id="independentAgentContract"' in html
    assert "state.agentContracts[action]" in script
    assert "function renderCreativeQuality" in script


def test_workbench_uses_stage_views_without_changing_workflow_nodes() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    script = Path("web/app.js").read_text(encoding="utf-8")
    for view in ("projects", "assets", "script", "storyboard", "production", "delivery"):
        assert f'data-view="{view}"' in html
        assert f'data-view-section="{view}"' in html
    assert 'id="continueProject"' in html
    assert "function viewForStage(stage)" in script
    assert "function continueCurrentProject()" in script
    assert 'id="crawlTargetText"' in html
    assert "function updateCrawlTargetUI()" in script
    assert "data-delete-project" in script
    assert "contextmenu" in script
    assert "voiceover_zh" in script
    assert "seedance_prompt_zh" in script
    assert 'id="saveShotsAndContinue"' in script
