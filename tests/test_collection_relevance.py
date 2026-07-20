from tools.collect import relevance


def test_keyword_relevance_accepts_exact_and_alias_matches() -> None:
    exact = relevance.score_item(
        {"title": "Heated Cup Review", "caption": "A heated cup for night feeds"},
        "heated cup",
    )
    alias = relevance.score_item(
        {"caption": "Portable bottle warmer for travel and late-night feeding"},
        "heated cup",
    )

    assert exact["relevant"] is True
    assert exact["score"] >= 0.35
    assert alias["relevant"] is True
    assert "bottle warmer" in alias["matched_terms"]


def test_keyword_relevance_rejects_unrelated_video() -> None:
    result = relevance.score_item(
        {"title": "Summer makeup", "caption": "Dance challenge and beauty routine", "hashtags": ["beauty"]},
        "heated cup",
    )

    assert result["relevant"] is False
    assert result["score"] == 0.0


def test_chinese_keyword_expands_to_product_aliases() -> None:
    result = relevance.score_item(
        {"caption": "新手父母夜间使用便携温奶器冲奶体验"},
        "恒温杯",
    )

    assert result["relevant"] is True


def test_account_and_trending_targets_are_trusted_by_discovery_scope() -> None:
    assert relevance.score_item({"caption": "anything"}, "creator", target_type="account")["relevant"] is True
    assert relevance.score_item({"caption": "anything"}, "", target_type="trending")["relevant"] is True
