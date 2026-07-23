from __future__ import annotations

import json
from pathlib import Path

from tools.collect import product_library


def test_product_library_indexes_ready_product(tmp_path: Path) -> None:
    root, white_hero = _sample_product_root(tmp_path)
    index_path = tmp_path / "index.json"

    payload = product_library.refresh_index([root], path=index_path)

    product = _only_product(payload)
    assert product["id"] == "便携恒温杯"
    assert product["ready"] is True
    assert product["seedance_source"] == white_hero.as_posix()
    assert product["counts"]["product_identity"] == 1
    assert product["counts"]["scene"] == 1
    assert product["counts"]["usage_step"] == 1
    assert not [issue for issue in product["issues"] if issue["severity"] == "BLOCKED"]
    assert index_path.is_file()


def test_product_library_blocks_without_white_hero(tmp_path: Path) -> None:
    root = tmp_path / "产品资料"
    root.mkdir()
    (root / "便携恒温杯.md").write_text("# 便携恒温杯\n", encoding="utf-8")
    scene_dir = root / "便携恒温杯" / "listing-0602-nw" / "产品场景使用图"
    scene_dir.mkdir(parents=True)
    (scene_dir / "场景图1.jpg").write_bytes(b"jpg")

    payload = product_library.refresh_index([root], path=tmp_path / "index.json")

    product = _only_product(payload)
    assert product["ready"] is False
    assert product["seedance_source"] == ""
    assert "missing_white_hero" in {issue["code"] for issue in product["issues"]}


def test_product_library_ignores_operational_notes(tmp_path: Path) -> None:
    root, _ = _sample_product_root(tmp_path)
    (root / "618大促期间竞品动作.md").write_text("# 运营宣传\n", encoding="utf-8")
    (root / "产品篇-讲产品本身是什么.md").write_text("# 运营宣传\n", encoding="utf-8")
    (root / "卡审原因分析.md").write_text("# 流程复盘\n", encoding="utf-8")

    payload = product_library.refresh_index([root], path=tmp_path / "index.json")

    ids = {product["id"] for product in payload["products"]}
    assert ids == {"便携恒温杯"}


def test_product_library_can_allow_new_sku_by_env(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "产品资料"
    root.mkdir()
    (root / "新硬件产品.md").write_text("# 新硬件产品\n", encoding="utf-8")
    monkeypatch.setenv("VAF_PRODUCT_LIBRARY_PRODUCTS", "新硬件产品")

    payload = product_library.refresh_index([root], path=tmp_path / "index.json")

    assert {product["id"] for product in payload["products"]} == {"新硬件产品"}


def test_product_library_loads_machine_readable_temperature_fact(tmp_path: Path) -> None:
    root, _ = _sample_product_root(tmp_path)
    (root / "便携恒温杯.yaml").write_text(
        "product_id: 便携恒温杯\ndisplay:\n  approved_value: '98°F'\n  temperature_scale: Fahrenheit\n",
        encoding="utf-8",
    )

    payload = product_library.refresh_index([root], path=tmp_path / "index.json")

    product = _only_product(payload)
    assert product["facts"]["display"]["approved_value"] == "98°F"
    assert product["facts"]["display"]["temperature_scale"] == "Fahrenheit"


def test_product_guardrail_text_exposes_fahrenheit_rule(tmp_path: Path, monkeypatch) -> None:
    root, _ = _sample_product_root(tmp_path)
    index_path = tmp_path / "index.json"
    (root / "便携恒温杯.yaml").write_text(
        "product_id: 便携恒温杯\ndisplay:\n  approved_value: '98°F'\n  forbidden_values: ['98°C']\n",
        encoding="utf-8",
    )
    product_library.refresh_index([root], path=index_path)
    monkeypatch.setenv("VAF_PRODUCT_LIBRARY_INDEX", str(index_path))

    guardrails = product_library.product_guardrail_text("便携恒温杯")

    assert "98°F" in guardrails
    assert "98°C" in guardrails


def test_generation_references_include_approved_usage_step(tmp_path: Path, monkeypatch) -> None:
    root, _ = _sample_product_root(tmp_path)
    index_path = tmp_path / "index.json"
    product_library.refresh_index([root], path=index_path)
    monkeypatch.setenv("VAF_PRODUCT_LIBRARY_INDEX", str(index_path))

    references = product_library.resolve_generation_references("便携恒温杯")

    assert len(references) == 1
    assert references[0].endswith("倒出口参考.png")


def test_unknown_product_never_falls_back_to_warming_cup_identity(tmp_path: Path, monkeypatch) -> None:
    index_path = tmp_path / "index.json"
    index_path.write_text(
        '{"version":"2.0","generated_at":null,"source_roots":[],"products":[]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("VAF_PRODUCT_LIBRARY_INDEX", str(index_path))

    assert product_library.resolve_seedance_source("折叠雨伞") == ""
    assert product_library.resolve_generation_references("折叠雨伞") == []


def _sample_product_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "产品资料"
    root.mkdir()
    (root / "便携恒温杯.md").write_text("# 便携恒温杯\n", encoding="utf-8")
    product_dir = root / "便携恒温杯" / "listing-0602-nw"
    main_dir = product_dir / "主图"
    scene_dir = product_dir / "产品场景使用图"
    main_dir.mkdir(parents=True)
    scene_dir.mkdir(parents=True)
    white_hero = main_dir / "白底主图.png"
    white_hero.write_bytes(b"png")
    (main_dir / "倒出口参考.png").write_bytes(b"png")
    (scene_dir / "场景图1.jpg").write_bytes(b"jpg")
    return root, white_hero


def _only_product(payload: dict) -> dict:
    assert len(payload["products"]) == 1
    return payload["products"][0]
def test_product_guardrails_include_company_content_profile(tmp_path, monkeypatch) -> None:
    product_path = tmp_path / "index.json"
    product_path.write_text(
        json.dumps(
            {
                "products": [
                    {
                        "id": "吸奶器",
                        "facts": {"approved_facts": ["自研活塞泵"]},
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VAF_PRODUCT_LIBRARY_INDEX", str(product_path))
    monkeypatch.setattr(
        product_library,
        "brand_profile",
        lambda path=None: {"brand": "熊猫布布", "content_voice": ["自然、克制、可验证"]},
    )

    payload = json.loads(product_library.product_guardrail_text("吸奶器"))

    assert payload["approved_facts"] == ["自研活塞泵"]
    assert payload["brand_profile"]["brand"] == "熊猫布布"
