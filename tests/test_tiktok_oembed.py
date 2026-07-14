from __future__ import annotations

from pathlib import Path

from tools.collect import manual_import, tiktok_oembed


def test_oembed_collector_enriches_and_imports_metadata(tmp_path: Path) -> None:
    def fake_fetch(url: str) -> dict[str, object]:
        assert url.endswith("7123456789012345678")
        return {
            "title": "Warm milk on the go #travel #bottle",
            "author_name": "Demo Creator",
            "author_url": "https://www.tiktok.com/@demo",
            "thumbnail_url": "https://example.com/cover.jpg",
        }

    result = tiktok_oembed.collect_links(
        [{"url": "https://www.tiktok.com/@demo/video/7123456789012345678"}],
        product_id="便携恒温杯",
        source_keyword="thermos_reference",
        library_root=str(tmp_path),
        fetch_json=fake_fetch,
    )

    assert result["provider"] == "tiktok_oembed"
    assert result["resolved_count"] == 1
    assert result["failed_count"] == 0
    meta = manual_import.load_material_meta("tt_7123456789012345678", tmp_path)
    assert meta["caption"] == "Warm milk on the go #travel #bottle"
    assert meta["author_name"] == "Demo Creator"
    assert meta["cover_url"] == "https://example.com/cover.jpg"
    assert meta["hashtags"] == ["travel", "bottle"]
    assert meta["processing_status"] == "needs_review"
    assert "engagement metrics" in meta["asset_intake"]["notes"]


def test_oembed_collector_rejects_non_tiktok_urls(tmp_path: Path) -> None:
    try:
        tiktok_oembed.collect_links(
            [{"url": "https://example.com/video/1"}],
            product_id="便携恒温杯",
            source_keyword="test",
            library_root=str(tmp_path),
            fetch_json=lambda _: {},
        )
    except ValueError as exc:
        assert "unsupported TikTok URL" in str(exc)
    else:
        raise AssertionError("non-TikTok URL should be rejected")
