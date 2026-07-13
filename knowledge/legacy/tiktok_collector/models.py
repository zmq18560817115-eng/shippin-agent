from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field


class TikTokVideoRecord(BaseModel):
    video_url: str
    video_id: str
    caption: str = ""
    author_name: str = ""
    author_url: str = ""
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    collect_count: int = 0
    publish_time: str | None = None
    hashtags: list[str] = Field(default_factory=list)
    music_title: str = ""
    cover_url: str = ""
    source_keyword: str
    crawl_time: str
    processing_status: str = "raw"
    transcript_text: str = ""
    ai_analysis_json: str = ""
    local_video_path: str = ""


class ReviewedTikTokVideoRecord(TikTokVideoRecord):
    clean_status: str = "kept"
    relevance_score: int = 0
    clean_reasons: list[str] = Field(default_factory=list)


class CollectRequest(BaseModel):
    keywords: list[str] = Field(min_length=1)
    limit_per_keyword: int = Field(default=50, ge=1, le=200)
    export_json: bool = True
    export_csv: bool = True


class ExportArtifacts(BaseModel):
    json_path: str | None = None
    csv_path: str | None = None
    clean_json_path: str | None = None
    clean_csv_path: str | None = None
    review_json_path: str | None = None


class CollectResponse(BaseModel):
    keywords: list[str]
    limit_per_keyword: int
    total_records: int
    kept_records: int = 0
    dropped_records: int = 0
    records: list[TikTokVideoRecord]
    clean_records: list[ReviewedTikTokVideoRecord] = Field(default_factory=list)
    dropped_items: list[ReviewedTikTokVideoRecord] = Field(default_factory=list)
    artifacts: ExportArtifacts
    started_at: str
    finished_at: str
    db_enabled: bool = False
    db_upserted: int = 0


class CollectRunResult(BaseModel):
    response: CollectResponse
    json_file: Path | None = None
    csv_file: Path | None = None
    clean_json_file: Path | None = None
    clean_csv_file: Path | None = None
    review_json_file: Path | None = None
