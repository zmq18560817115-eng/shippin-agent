from __future__ import annotations

import re
from typing import Any


TOKEN_RE = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]+", re.IGNORECASE)

QUERY_EXPANSIONS = {
    "heated cup": ("bottle warmer", "portable warmer", "milk warmer", "formula warmer", "breast milk warmer"),
    "恒温杯": ("温奶器", "暖奶器", "恒温壶", "便携温奶", "bottle warmer", "milk warmer", "portable bottle warmer"),
    "便携恒温杯": ("恒温杯", "温奶器", "暖奶器", "便携温奶", "portable bottle warmer", "travel bottle warmer"),
    "温奶器": ("暖奶器", "恒温杯", "bottle warmer", "milk warmer", "formula warmer", "portable bottle warmer"),
}

NEGATIVE_TERMS = {
    "恒温杯": ("coffee mug", "coffee warmer", "soldering", "python", "qr code", "makeup", "dance"),
    "便携恒温杯": ("coffee mug", "coffee warmer", "soldering", "python", "qr code", "makeup", "dance"),
    "温奶器": ("coffee mug", "coffee warmer", "soldering", "python", "qr code", "makeup", "dance"),
}


def query_plan(target: str, *, target_type: str = "keyword", limit: int = 8) -> list[str]:
    """Return focused discovery queries in priority order.

    TikTok hashtag discovery is not a real full-text search. Splitting a product
    intent into several focused English/Chinese tags gives substantially better
    recall while post-discovery scoring keeps unrelated results out of the library.
    """
    if target_type not in {"keyword", "hashtag"}:
        return [target] if target else []
    normalized = _normalize(target.lstrip("#"))
    candidates = [normalized, *QUERY_EXPANSIONS.get(normalized, ())]
    output: list[str] = []
    for candidate in candidates:
        value = _normalize(candidate)
        if value and value not in output:
            output.append(value)
        if len(output) >= max(1, limit):
            break
    return output


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
    negative_matches = _negative_matches(item, target)
    penalty = min(0.65, 0.35 * len(negative_matches))
    # A full product alias in one strong metadata field is sufficient evidence;
    # field weights should not accidentally push an exact caption match below
    # the production intake threshold.
    if matched:
        score = max(score, 0.6)
    normalized = round(max(0.0, min(1.0, score - penalty)), 4)
    return {
        "score": normalized,
        "matched_terms": sorted(matched),
        "negative_terms": negative_matches,
        "relevant": normalized >= 0.35 and not negative_matches,
    }


def quality_score(item: dict[str, Any], relevance_result: dict[str, Any]) -> dict[str, Any]:
    """Rank a relevant candidate by demand signal and metadata completeness."""
    relevance_value = float(relevance_result.get("score") or 0.0)
    plays = _positive_int(item.get("play_count"))
    likes = _positive_int(item.get("like_count"))
    comments = _positive_int(item.get("comment_count"))
    shares = _positive_int(item.get("share_count"))
    engagement = likes + comments * 3 + shares * 5
    popularity = min(1.0, plays / 500_000) if plays else min(1.0, engagement / 25_000)
    engagement_rate = min(1.0, engagement / max(plays, 1) / 0.08) if plays else min(1.0, engagement / 5_000)
    completeness = sum(
        bool(item.get(field))
        for field in ("caption", "author_name", "cover_url", "url")
    ) / 4
    score = round(relevance_value * 0.62 + popularity * 0.2 + engagement_rate * 0.1 + completeness * 0.08, 4)
    return {
        "score": score,
        "relevance_score": round(relevance_value, 4),
        "popularity_score": round(popularity, 4),
        "engagement_score": round(engagement_rate, 4),
        "metadata_score": round(completeness, 4),
        "play_count": plays,
        "engagement_count": engagement,
    }


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


def _negative_matches(item: dict[str, Any], target: str) -> list[str]:
    normalized_target = _normalize(target)
    terms = NEGATIVE_TERMS.get(normalized_target, ())
    haystack = _normalize(" ".join([
        str(item.get("title") or ""),
        str(item.get("caption") or item.get("description") or ""),
        " ".join(str(value) for value in (item.get("hashtags") or [])),
    ]))
    return sorted({term for term in terms if _normalize(term) in haystack})


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
