from libshared.agent_contracts import AGENT_CONTRACTS, agent_system_prompt
from orchestrator.capabilities import capability_map


def test_every_model_agent_has_actionable_contract() -> None:
    for agent_id in ("analysis", "research", "strategy", "script", "storyboard", "production", "review", "feedback"):
        contract = AGENT_CONTRACTS[agent_id]
        assert contract["identity"]
        assert contract["mission"]
        assert len(contract["quality_gates"]) >= 3
        assert len(contract["forbidden"]) >= 2


def test_system_prompt_carries_identity_quality_and_grounding() -> None:
    prompt = agent_system_prompt("storyboard")

    assert "电影级分镜导演" in prompt
    assert "交付前必须自检" in prompt
    assert "竞品素材仅可借鉴结构" in prompt
    assert "简体中文" in prompt


def test_capability_map_exposes_agent_contract_to_frontend() -> None:
    agents = {item["id"]: item for item in capability_map()["agents"]}

    assert agents["script"]["identity"] == "广告剧情编剧与短视频导演"
    assert "五段剧情因果连续" in agents["script"]["quality_gates"]
    assert "五镜重复同一构图" in agents["storyboard"]["forbidden"]
