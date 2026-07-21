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
    assert 'id="independentCreativeStyle"' in html
    assert 'id="independentTargetAudience"' in html
    assert 'id="independentCreativeFreedom"' in html
    assert "state.agentContracts[action]" in script
    assert "function creativeRequestFields()" in script
    assert "...creativeRequestFields()" in script
    assert "agentExecutionContext" in script
    assert 'class="creativeOptions"' in html
    assert "查看能力与质量标准" in script
    assert "function renderCreativeQuality" in script


def test_workbench_uses_stage_views_without_changing_workflow_nodes() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    script = Path("web/app.js").read_text(encoding="utf-8")
    for view in ("projects", "assets", "script", "storyboard", "production", "delivery"):
        assert f'data-view="{view}"' in html
        if view == "delivery":
            assert 'data-view-section="archive delivery"' in html
        else:
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


def test_video_project_navigation_exposes_every_production_stage() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    script = Path("web/app.js").read_text(encoding="utf-8")

    for view in ("projects", "strategy", "script", "storyboard", "production", "review", "archive"):
        assert f'data-view="{view}"' in html
        assert view in script

    assert 'id="strategyNode" data-view-section="strategy"' in html
    assert 'id="scriptGate" data-view-section="script"' in html
    assert 'id="composeNode" data-view-section="review"' in html
    assert 'id="deliveryNode" data-view-section="archive delivery"' in html
    assert 'id="runStrategy"' in html
    assert 'id="composePanel"' in html
    assert 'id="deliveryPanel"' in html
    assert 'showView("archive")' in script
    assert 'section.dataset.viewSection.split(/\\s+/).includes(next)' in script


def test_p0_information_architecture_is_exposed_as_first_class_views() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    script = Path("web/app.js").read_text(encoding="utf-8")
    styles = Path("web/styles.css").read_text(encoding="utf-8")

    for view in ("home", "tools", "tasks"):
        assert f'data-view="{view}"' in html
        assert f'data-view-section="{view}"' in html

    for action in (
        "analysis",
        "strategy",
        "script",
        "script_breakdown",
        "storyboard",
        "production",
    ):
        assert f'data-tool-action="{action}"' in html

    for task_filter in ("running", "human", "failed", "done"):
        assert f'data-task-filter="{task_filter}"' in html

    assert 'id="homeContinue"' in html
    assert 'id="homeNewProject"' in html
    assert 'id="homeProjects"' in html
    assert 'id="homeTasks"' in html
    assert "function renderHomeDashboard" in script
    assert "function renderTaskCenter" in script
    assert "function runQuickTool" in script
    assert "[hidden]" in styles
    assert "display: none !important" in styles


def test_material_center_uses_five_focused_subsections() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    script = Path("web/app.js").read_text(encoding="utf-8")

    for area in ("products", "references", "collection", "analysis", "packages"):
        assert f'data-asset-area="{area}"' in html
        assert f'data-asset-panel="{area}"' in html

    assert 'id="projectAssetPackages"' in html
    assert 'id="projectAssetPackagePanel"' in html
    assert "function setAssetArea" in script
    assert "function renderProjectAssetPackages" in script
    assert 'api("/api/v2/collect/library?limit=50")' in script
    assert 'api("/api/v2/collect/jobs"' in script
