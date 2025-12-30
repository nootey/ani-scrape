from logging import Logger
from typing import List

from app.core.config import config
from app.core.database import DatabaseClient
from app.core.models import MediaType
from app.services.anilist_client import AniListClient
from app.services.discord_notifier import DiscordNotifier


class AniListSync:
    def __init__(self, logger: Logger, db: DatabaseClient):
        self.logger = logger.getChild("sync")
        self.db = db
        self.client = AniListClient(logger)
        self.notifier = DiscordNotifier(logger)

    async def sync_from_anilist(self):

        username = config.anilist.username
        if not username:
            self.logger.warning("No AniList username configured, skipping sync")
            return

        self.logger.info(f"Syncing subscriptions from AniList user: {username}")

        try:
            anime_list = await self.client.get_user_anime_list(username, "CURRENT")
            self.logger.info(f"Found {len(anime_list)} anime in WATCHING list")

            manga_list = await self.client.get_user_manga_list(username, "CURRENT")
            self.logger.info(f"Found {len(manga_list)} manga in READING list")

            total_synced = 0
            for media in anime_list + manga_list:
                media_type = MediaType.ANIME if media["type"] == "ANIME" else MediaType.MANGA

                await self.db.add_or_update_media(
                    anilist_id=media["id"],
                    media_type=media_type,
                    title_romaji=media["title_romaji"],
                    title_english=media["title_english"]
                )
                total_synced += 1

            self.logger.info(f"Synced {total_synced} total subscriptions from AniList")

            await self.cleanup_finished_series()

        except Exception as e:
            self.logger.error(f"Failed to sync from AniList: {e}")
            if config.discord.notify_on_error:
                self.notifier.send_error(f"AniList sync failed: {str(e)}")

    async def cleanup_finished_series(self):
        self.logger.info("Checking for series no longer in your AniList lists...")

        try:
            username = config.anilist.username
            if not username:
                return

            anime_list = await self.client.get_user_anime_list(username, "CURRENT")
            manga_list = await self.client.get_user_manga_list(username, "CURRENT")

            current_ids = {media["id"] for media in anime_list + manga_list}

            all_media = await self.db.get_all_tracked_media()
            removed_count = 0

            for media in all_media:
                media_id = media.anilist_id
                title = media.title_romaji

                if media_id not in current_ids:
                    await self.db.delete_media(media_id)
                    self.logger.info(f"Unsubscribed from {title}")
                    removed_count += 1

            if removed_count > 0:
                self.logger.info(f"Removed {removed_count} series no longer in your lists")
            else:
                self.logger.info("All subscriptions are still in your WATCHING/READING lists")

        except Exception as e:
            self.logger.error(f"Failed to cleanup series: {e}")
            if config.discord.notify_on_error:
                self.notifier.send_error(f"Anilist cleanup failed: {str(e)}")