from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, DateTime, Boolean, ForeignKey, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import enum


class Base(DeclarativeBase):
    pass


class MediaType(str, enum.Enum):
    ANIME = "ANIME"
    MANGA = "MANGA"

class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anilist_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)

    media_type: Mapped[MediaType] = mapped_column(SQLEnum(MediaType), nullable=False)

    title_romaji: Mapped[str] = mapped_column(String, nullable=False)
    title_english: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Tracking
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    releases: Mapped[list["Release"]] = relationship("Release", back_populates="media", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Media(id={self.id}, anilist_id={self.anilist_id}, title='{self.title_romaji}', type={self.media_type})>"


class Release(Base):
    __tablename__ = "releases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    media_id: Mapped[int] = mapped_column(Integer, ForeignKey("media.id", ondelete="CASCADE"), nullable=False)

    # Episode number (for anime) or chapter number (for manga)
    # Using Float to support decimals like 5.5
    number: Mapped[float] = mapped_column(Float, nullable=False)

    # When it was released (or detected)
    released_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Notification tracking
    notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    media: Mapped["Media"] = relationship("Media", back_populates="releases")

    __table_args__ = (
        UniqueConstraint('media_id', 'number', name='uq_media_release'),
        {"sqlite_autoincrement": True},
    )

    def __repr__(self):
        type_str = "Episode" if self.media.media_type == MediaType.ANIME else "Chapter"
        return f"<Release(id={self.id}, media_id={self.media_id}, {type_str}={self.number})>"


meta = Base.metadata