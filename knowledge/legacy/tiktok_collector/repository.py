from __future__ import annotations

import json

from .db import DatabaseManager, TikTokVideoORM
from .models import TikTokVideoRecord


class TikTokVideoRepository:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db

    @staticmethod
    def _row_to_record(row: TikTokVideoORM) -> TikTokVideoRecord:
        try:
            hashtags = json.loads(row.hashtags_json or "[]")
        except json.JSONDecodeError:
            hashtags = []
        if not isinstance(hashtags, list):
            hashtags = []
        return TikTokVideoRecord(
            video_url=row.video_url,
            video_id=row.video_id,
            caption=row.caption or "",
            author_name=row.author_name or "",
            author_url=row.author_url or "",
            like_count=int(row.like_count or 0),
            comment_count=int(row.comment_count or 0),
            share_count=int(row.share_count or 0),
            collect_count=int(row.collect_count or 0),
            publish_time=row.publish_time,
            hashtags=[str(tag) for tag in hashtags if str(tag).strip()],
            music_title=row.music_title or "",
            cover_url=row.cover_url or "",
            source_keyword=row.source_keyword or "",
            crawl_time=row.crawl_time or "",
            processing_status=row.processing_status or "raw",
            transcript_text=row.transcript_text or "",
            ai_analysis_json=row.ai_analysis_json or "",
            local_video_path=row.local_video_path or "",
        )

    def upsert_records(self, records: list[TikTokVideoRecord]) -> int:
        if not self.db.enabled or not records:
            return 0
        upserted = 0
        with self.db.session_scope() as session:
            for record in records:
                row = session.query(TikTokVideoORM).filter(TikTokVideoORM.video_id == record.video_id).one_or_none()
                payload = {
                    "video_url": record.video_url,
                    "video_id": record.video_id,
                    "caption": record.caption,
                    "author_name": record.author_name,
                    "author_url": record.author_url,
                    "like_count": record.like_count,
                    "comment_count": record.comment_count,
                    "share_count": record.share_count,
                    "collect_count": record.collect_count,
                    "publish_time": record.publish_time,
                    "hashtags_json": json.dumps(record.hashtags, ensure_ascii=False),
                    "music_title": record.music_title,
                    "cover_url": record.cover_url,
                    "source_keyword": record.source_keyword,
                    "crawl_time": record.crawl_time,
                    "processing_status": record.processing_status or "raw",
                    "transcript_text": record.transcript_text or "",
                    "ai_analysis_json": record.ai_analysis_json or "",
                    "local_video_path": record.local_video_path or "",
                }
                if row is None:
                    session.add(TikTokVideoORM(**payload))
                else:
                    for key, value in payload.items():
                        setattr(row, key, value)
                upserted += 1
        return upserted

    def list_records(
        self,
        *,
        q: str = "",
        source_keyword: str = "",
        processing_status: str = "",
        limit: int = 20,
        order_by: str = "recent",
    ) -> tuple[int, list[TikTokVideoRecord]]:
        if not self.db.enabled:
            return 0, []

        normalized_q = q.strip()
        normalized_source = source_keyword.strip()
        normalized_status = processing_status.strip()
        normalized_limit = max(1, min(100, int(limit)))

        with self.db.session_scope() as session:
            query = session.query(TikTokVideoORM)
            if normalized_q:
                like = f"%{normalized_q}%"
                query = query.filter(
                    TikTokVideoORM.caption.ilike(like)
                    | TikTokVideoORM.author_name.ilike(like)
                    | TikTokVideoORM.video_id.ilike(like)
                    | TikTokVideoORM.source_keyword.ilike(like)
                    | TikTokVideoORM.hashtags_json.ilike(like)
                )
            if normalized_source:
                query = query.filter(TikTokVideoORM.source_keyword == normalized_source)
            if normalized_status:
                query = query.filter(TikTokVideoORM.processing_status == normalized_status)

            total = query.count()
            hot_score = (
                TikTokVideoORM.like_count
                + TikTokVideoORM.comment_count
                + TikTokVideoORM.share_count
            )
            if (order_by or "").strip().lower() == "hot":
                order_clause = (hot_score.desc(), TikTokVideoORM.crawl_time.desc(), TikTokVideoORM.id.desc())
            else:
                order_clause = (TikTokVideoORM.created_at.desc(), TikTokVideoORM.id.desc())
            rows = query.order_by(*order_clause).limit(normalized_limit).all()
            return total, [self._row_to_record(row) for row in rows]
