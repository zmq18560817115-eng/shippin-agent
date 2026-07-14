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
