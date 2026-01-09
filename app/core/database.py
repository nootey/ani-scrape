import threading
from asyncio import current_task
from datetime import datetime
from logging import Logger
from typing import Optional, List

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import joinedload

from app.core.models import MediaType, Media, Base, Release


class DatabaseClient:
    def __init__(self, url: str, logger: Logger):
        self.db_connections = threading.local()
        self.url = url
        self.logger = logger.getChild("database")

    def async_engine(self) -> AsyncEngine:
        if not hasattr(self.db_connections, "engine"):
            self.logger.debug("Starting engine.")
            self.db_connections.engine = create_async_engine(self.url)
            self.logger.debug("Creating database engine finished.")
        return self.db_connections.engine

    def async_session_factory(self) -> async_sessionmaker:
        self.logger.debug("Starting session factory.")
        if not hasattr(self.db_connections, "session_factory"):
            engine = self.async_engine()
            self.db_connections.session_factory = async_sessionmaker(bind=engine)
        return self.db_connections.session_factory

    def async_scoped_session(self) -> async_scoped_session[AsyncSession]:
        self.logger.debug("Getting scoped session.")
        if not hasattr(self.db_connections, "scoped_session"):
            session_factory = self.async_session_factory()
            self.db_connections.scoped_session = async_scoped_session(
                session_factory, scopefunc=current_task
            )
        return self.db_connections.scoped_session

    async def cleanup(self):
        self.logger.debug("Cleaning database engine.")

        await self.db_connections.engine.dispose()
        self.logger.debug("Cleaning database finished.")

    async def create_models(self):
        self.logger.debug("Creating ORM modules.")
        async with self.async_engine().begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.logger.debug("Finished creating ORM modules.")

    async def add_or_update_media(
        self,
        anilist_id: int,
        media_type: MediaType,
        title_romaji: str,
        title_english: Optional[str] = None,
    ) -> Media:
        session = self.async_scoped_session()

        stmt = select(Media).where(Media.anilist_id == anilist_id)
        result = await session.execute(stmt)
        media = result.scalar_one_or_none()

        if media:
            # Update existing
            media.title_romaji = title_romaji
            media.title_english = title_english
            media.last_updated_at = datetime.utcnow()
            self.logger.debug(f"Updated media: {title_romaji}")
        else:
            # Create new
            media = Media(
                anilist_id=anilist_id,
                media_type=media_type,
                title_romaji=title_romaji,
                title_english=title_english,
                last_updated_at=datetime.utcnow(),
            )
            session.add(media)
            self.logger.debug(f"Added new media: {title_romaji}")

        await session.commit()
        await session.refresh(media)
        return media

    async def get_all_tracked_media(
        self, media_type: Optional[MediaType] = None
    ) -> List[Media]:
        session = self.async_scoped_session()
        stmt = select(Media)

        if media_type:
            stmt = stmt.where(Media.media_type == media_type)

        stmt = stmt.order_by(Media.title_romaji)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def delete_media(self, anilist_id: int) -> bool:
        session = self.async_scoped_session()
        stmt = select(Media).where(Media.anilist_id == anilist_id)
        result = await session.execute(stmt)
        media = result.scalar_one_or_none()

        if media:
            title = media.title_romaji
            await session.delete(media)
            await session.commit()
            self.logger.info(f"Deleted media: {title}")
            return True
        return False

    async def add_release(
        self, media_id: int, number: float, released_at: Optional[datetime] = None
    ) -> tuple[Release, bool]:
        session = self.async_scoped_session()

        stmt = select(Release).where(
            and_(Release.media_id == media_id, Release.number == number)
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            return existing, False

        release = Release(
            media_id=media_id,
            number=number,
            released_at=released_at or datetime.utcnow(),
        )
        session.add(release)
        await session.commit()
        await session.refresh(release)

        self.logger.info(f"New release {number} added for media_id={media_id}")

        return release, True

    async def get_latest_release_number(self, media_id: int) -> Optional[float]:
        session = self.async_scoped_session()
        stmt = select(func.max(Release.number)).where(Release.media_id == media_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_unnotified_releases(self) -> List[Release]:
        session = self.async_scoped_session()
        stmt = (
            select(Release)
            .options(joinedload(Release.media))
            .where(Release.notified.is_(False))
            .order_by(Release.created_at.desc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def mark_as_notified(self, release_id: int):
        session = self.async_scoped_session()

        from sqlalchemy import update

        stmt = (
            update(Release)
            .where(Release.id == release_id)
            .values(notified=True, notified_at=datetime.utcnow())
        )
        await session.execute(stmt)
        await session.commit()

        self.logger.debug(f"Marked release {release_id} as notified")
