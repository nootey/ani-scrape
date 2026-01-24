from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    Integer,
    Float,
    DateTime,
    Enum as SQLEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
import enum


class Base(DeclarativeBase):
    pass


class MediaType(str, enum.Enum):
    ANIME = "ANIME"
    MANGA = "MANGA"


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anilist_id: Mapped[int] = mapped_column(
        Integer, unique=True, nullable=False, index=True
    )
    mangaupdates_id: Mapped[Optional[int]] = mapped_column(nullable=True)

    media_type: Mapped[MediaType] = mapped_column(SQLEnum(MediaType), nullable=False)

    title_romaji: Mapped[str] = mapped_column(String, nullable=False)
    title_english: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # User's progress (episodes watched / chapters read)
    user_progress: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=None
    )

    # Last known total count from AniList
    last_checked_count: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, default=None
    )

    # Tracking
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    def __repr__(self):
        return f"<Media(id={self.id}, anilist_id={self.anilist_id}, title='{self.title_romaji}', type={self.media_type})>"


meta = Base.metadata
