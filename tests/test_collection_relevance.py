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


def test_keyword_relevance_rejects_single_generic_alias_token() -> None:
    result = relevance.score_item(
        {
            "title": "Portable phone tripod",
            "caption": "A portable creator stand for travel videos",
            "hashtags": ["portable", "creator"],
        },
        "heated cup",
    )

    assert result["relevant"] is False
    assert "portable bottle warmer" not in result["matched_terms"]


def test_keyword_relevance_accepts_multi_token_alias_without_exact_phrase() -> None:
    result = relevance.score_item(
        {"caption": "A travel bottle heater and warmer for night feeds"},
        "heated cup",
    )

    assert result["relevant"] is True
    assert "bottle warmer" in result["matched_terms"]


def test_chinese_keyword_expands_to_product_aliases() -> None:
    result = relevance.score_item(
        {"caption": "新手父母夜间使用便携温奶器冲奶体验"},
        "恒温杯",
    )

    assert result["relevant"] is True


def test_account_and_trending_targets_are_trusted_by_discovery_scope() -> None:
    assert relevance.score_item({"caption": "anything"}, "creator", target_type="account")["relevant"] is True
    assert relevance.score_item({"caption": "anything"}, "", target_type="trending")["relevant"] is True


def test_product_query_plan_expands_bilingual_purchase_intent() -> None:
    queries = relevance.query_plan("便携恒温杯")

    assert queries[0] == "便携恒温杯"
    assert "portable bottle warmer" in queries
    assert "travel bottle warmer" in queries


def test_negative_topic_blocks_false_positive_even_with_product_term() -> None:
    result = relevance.score_item(
        {"caption": "Python heated cup QR code tutorial", "hashtags": ["python", "qrcode"]},
        "恒温杯",
    )

    assert result["relevant"] is False
    assert "python" in result["negative_terms"]


def test_quality_score_rewards_relevant_popular_complete_video() -> None:
    relevant = {"score": 0.9, "relevant": True}
    strong = relevance.quality_score(
        {
            "url": "https://www.tiktok.com/@demo/video/1",
            "caption": "portable bottle warmer",
            "author_name": "demo",
            "cover_url": "https://example.test/cover.jpg",
            "play_count": 600000,
            "like_count": 50000,
            "comment_count": 1000,
            "share_count": 2000,
        },
        relevant,
    )
    weak = relevance.quality_score({"url": "https://www.tiktok.com/@demo/video/2"}, relevant)

    assert strong["score"] > weak["score"]
    assert strong["play_count"] == 600000
