from __future__ import annotations

import re
from typing import Any


TOKEN_RE = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]+", re.IGNORECASE)

QUERY_EXPANSIONS = {
    "heated cup": ("bottle warmer", "portable warmer", "milk warmer", "formula warmer", "breast milk warmer"),
    "恒温杯": ("温奶器", "暖奶器", "恒温壶", "便携温奶", "bottle warmer", "milk warmer"),
    "温奶器": ("暖奶器", "恒温杯", "bottle warmer", "milk warmer", "formula warmer"),
}


def score_item(item: dict[str, Any], target: str, *, target_type: str = "keyword") -> dict[str, Any]:
    if target_type in {"account", "trending"}:
        return {"score": 1.0, "matched_terms": [target] if target else [], "relevant": True}

    terms = _query_terms(target)
    fields = {
        "title": str(item.get("title") or item.get("video_title") or ""),
        "caption": str(item.get("caption") or item.get("description") or ""),
        "hashtags": " ".join(str(value) for value in (item.get("hashtags") or [])),
        "author": str(item.get("author_name") or item.get("author") or ""),
    }
    weights = {"title": 0.42, "caption": 0.38, "hashtags": 0.15, "author": 0.05}
    matched: set[str] = set()
    score = 0.0
    for name, text in fields.items():
        field_score, field_matches = _field_score(text, terms)
        score += weights[name] * field_score
        matched.update(field_matches)
    normalized = round(min(1.0, score), 4)
    return {"score": normalized, "matched_terms": sorted(matched), "relevant": normalized >= 0.35}


def _query_terms(target: str) -> list[str]:
    normalized = _normalize(target.lstrip("#"))
    candidates = [normalized, *QUERY_EXPANSIONS.get(normalized, ())]
    terms: list[str] = []
    for candidate in candidates:
        value = _normalize(candidate)
        if value and value not in terms:
            terms.append(value)
    return terms


def _field_score(text: str, terms: list[str]) -> tuple[float, set[str]]:
    normalized = _normalize(text)
    if not normalized or not terms:
        return 0.0, set()
    text_tokens = set(TOKEN_RE.findall(normalized))
    matched: set[str] = set()
    best = 0.0
    for term in terms:
        if term in normalized:
            matched.add(term)
            best = max(best, 1.0)
            continue
        term_tokens = set(TOKEN_RE.findall(term))
        if not term_tokens:
            continue
        overlap = len(term_tokens & text_tokens) / len(term_tokens)
        if overlap > 0:
            matched.add(term)
            best = max(best, overlap)
    return best, matched


def _normalize(value: str) -> str:
    return " ".join(str(value or "").casefold().replace("_", " ").replace("-", " ").split())
