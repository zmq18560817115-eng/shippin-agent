from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import ReviewedTikTokVideoRecord, TikTokVideoRecord


CSV_FIELDS = [
    "video_url",
    "video_id",
    "caption",
    "author_name",
    "author_url",
    "like_count",
    "comment_count",
    "share_count",
    "collect_count",
    "publish_time",
    "hashtags",
    "music_title",
    "cover_url",
    "source_keyword",
    "crawl_time",
]


def export_json(path: Path, records: list[TikTokVideoRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [record.model_dump(mode="json") for record in records]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_csv(path: Path, records: list[TikTokVideoRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for record in records:
            row = record.model_dump(mode="json")
            row["hashtags"] = json.dumps(row.get("hashtags") or [], ensure_ascii=False)
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def export_review_json(
    path: Path,
    kept: list[ReviewedTikTokVideoRecord],
    dropped: list[ReviewedTikTokVideoRecord],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "kept_records": [record.model_dump(mode="json") for record in kept],
        "dropped_records": [record.model_dump(mode="json") for record in dropped],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
