from pathlib import Path


def test_manual_stage_uses_existing_runtime_mode_control() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    script = Path("web/app.js").read_text(encoding="utf-8")

    assert 'id="runtimeMode"' in html
    assert '$("#runtimeMode").value' in script
    assert '$("#runMode")' not in script


def test_agent_capability_map_is_wired_into_workbench() -> None:
    html = Path("web/index.html").read_text(encoding="utf-8")
    script = Path("web/app.js").read_text(encoding="utf-8")

    assert 'id="agentMap"' in html
    assert 'id="agentMapPanel"' in html
    assert "data-agent-action" in script
    assert 'api("/api/v2/agents/run"' in script
