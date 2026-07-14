from __future__ import annotations

from tools.llm.doubao_script import _clean_voiceover


def test_voiceover_cleaner_removes_absolute_guarantee_language() -> None:
    cleaned = _clean_voiceover("Never settle for cold drinks again!")
    assert "never" not in cleaned.casefold()
    assert cleaned == "Make room for cold drinks again!"
