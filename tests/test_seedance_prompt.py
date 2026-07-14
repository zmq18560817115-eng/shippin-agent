from tools.providers.ark import _seedance_prompt


def test_seedance_prompt_uses_official_ratio_and_duration_flags() -> None:
    prompt = _seedance_prompt("Product demo", 5)
    assert "--ratio 9:16" in prompt
    assert "--dur 5" in prompt
