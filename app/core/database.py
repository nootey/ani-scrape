import threading
from asyncio import current_task
from datetime import datetime
from logging import Logger
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_scoped_session,
    async_sessionmaker,
    create_async_engine,
)

from app.core.models import MediaType, Media, Base


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
        user_progress: Optional[float] = None,
    ) -> Media:
        session = self.async_scoped_session()

        stmt = select(Media).where(Media.anilist_id == anilist_id)
        result = await session.execute(stmt)
        media = result.scalar_one_or_none()

        if media:
            # Update existing
            media.title_romaji = title_romaji
            media.title_english = title_english
            if user_progress is not None:
                media.user_progress = user_progress
            media.last_updated_at = datetime.utcnow()
            self.logger.info(f"Updated media: {title_romaji}")
        else:
            # Create new
            media = Media(
                anilist_id=anilist_id,
                media_type=media_type,
                title_romaji=title_romaji,
                title_english=title_english,
                user_progress=user_progress,
                last_updated_at=datetime.utcnow(),
            )
            session.add(media)
            self.logger.info(f"Added new media: {title_romaji}")

        await session.commit()
        await session.refresh(media)
        return media

    async def update_media_count(self, media_id: int, new_count: float):
        """Update the last checked count for a media"""
        from sqlalchemy import update

        session = self.async_scoped_session()

        stmt = (
            update(Media)
            .where(Media.id == media_id)
            .values(last_checked_count=new_count, last_updated_at=datetime.utcnow())
        )
        await session.execute(stmt)
        await session.commit()

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
