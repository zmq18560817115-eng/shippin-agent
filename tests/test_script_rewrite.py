from __future__ import annotations

from tools.llm.doubao_script import _clean_voiceover, _normalize_sections


def test_voiceover_cleaner_removes_absolute_guarantee_language() -> None:
    cleaned = _clean_voiceover("Never settle for cold drinks again!")
    assert "never" not in cleaned.casefold()
    assert cleaned == "Make room for cold drinks again!"


def test_real_script_contract_targets_30_seconds() -> None:
    sections = _normalize_sections([])
    assert len(sections) == 5
    assert [section["timing"] for section in sections] == [
        "0-6s",
        "6-12s",
        "12-18s",
        "18-24s",
        "24-30s",
    ]
