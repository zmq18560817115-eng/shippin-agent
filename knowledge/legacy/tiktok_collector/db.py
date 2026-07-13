from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import CollectorSettings


class Base(DeclarativeBase):
    pass


class TikTokVideoORM(Base):
    __tablename__ = "tiktok_videos"
    __table_args__ = (UniqueConstraint("video_id", name="uq_tiktok_videos_video_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_url: Mapped[str] = mapped_column(Text, nullable=False)
    video_id: Mapped[str] = mapped_column(String(64), nullable=False)
    caption: Mapped[str] = mapped_column(Text, default="", nullable=False)
    author_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    author_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    like_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    share_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    collect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    publish_time: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hashtags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    music_title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    cover_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    crawl_time: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), default="raw", nullable=False)
    transcript_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ai_analysis_json: Mapped[str] = mapped_column(Text, default="", nullable=False)
    local_video_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class DatabaseManager:
    def __init__(self, settings: CollectorSettings) -> None:
        self.settings = settings
        self.enabled = bool(settings.mysql_url)
        self.engine = None
        self.session_factory: sessionmaker[Session] | None = None
        self._initialized = False
        if self.enabled:
            self.engine = create_engine(settings.mysql_url, echo=settings.mysql_echo, future=True)
            self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def init_db(self) -> None:
        if not self.enabled or self.engine is None:
            raise RuntimeError("TIKTOK_COLLECTOR_MYSQL_URL 未配置，无法初始化数据库")
        Base.metadata.create_all(self.engine)
        self._initialized = True

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        if not self.enabled or self.session_factory is None:
            raise RuntimeError("数据库未启用")
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
