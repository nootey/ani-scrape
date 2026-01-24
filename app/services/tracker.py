from logging import Logger

from app.core.database import DatabaseClient
from app.core.models import MediaType
from app.services.anilist_client import AniListClient
from app.services.discord_notifier import DiscordNotifier
from app.core.config import config
from app.services.mangaupdates_client import MangaUpdatesClient


class ReleaseTracker:
    def __init__(self, logger: Logger, db: DatabaseClient):
        self.logger = logger.getChild("tracker")
        self.db = db
        self.client = AniListClient(logger)
        self.notifier = DiscordNotifier(logger)
        self.mu_client = MangaUpdatesClient(logger)

    async def check_for_updates(self):
        self.logger.info("Starting release check...")

        try:
            media_list = await self.db.get_all_tracked_media()

            if not media_list:
                self.logger.info("No media being tracked")
                return

            self.logger.info(f"Checking {len(media_list)} media for updates")

            notifications = []
            updates_to_make = []

            for media in media_list:
                # Skip if user hasn't logged any progress
                if not media.user_progress or media.user_progress == 0:
                    self.logger.debug(
                        f"Skipping {media.title_romaji} - no user progress logged"
                    )
                    continue

                try:
                    total_count = None

                    # ANIME: Always use AniList
                    if media.media_type == MediaType.ANIME:
                        try:
                            self.logger.debug(
                                f"Checking AniList for anime {media.title_romaji}"
                            )
                            media_info = await self.client.get_media_by_id(
                                media.anilist_id, "ANIME"
                            )
                            if media_info:
                                total_count = media_info.get("episodes")
                        except Exception as e:
                            self.logger.warning(
                                f"AniList failed for {media.title_romaji}: {e}"
                            )

                    # MANGA: Try MangaUpdates first, fallback to AniList
                    elif media.media_type == MediaType.MANGA:
                        try:
                            self.logger.debug(
                                f"Checking MangaUpdates for {media.title_romaji}"
                            )
                            mu_id = await self.mu_client.search_by_title(
                                media.title_romaji
                            )
                            if mu_id:
                                total_count = await self.mu_client.get_latest_chapter(
                                    mu_id
                                )
                                if total_count:
                                    self.logger.debug(
                                        f"MangaUpdates found {total_count} chapters"
                                    )
                        except Exception as e:
                            self.logger.warning(
                                f"MangaUpdates failed for {media.title_romaji}: {e}"
                            )

                        if not total_count:
                            try:
                                self.logger.debug(
                                    f"Falling back to AniList for manga {media.title_romaji}"
                                )
                                media_info = await self.client.get_media_by_id(
                                    media.anilist_id, "MANGA"
                                )
                                if media_info:
                                    total_count = media_info.get("chapters")
                            except Exception as e:
                                self.logger.warning(
                                    f"AniList fallback failed for {media.title_romaji}: {e}"
                                )

                    if not total_count:
                        self.logger.debug(
                            f"No count available for {media.title_romaji}, keeping previous value"
                        )
                        continue

                    # Check if this is the first time we're tracking this media
                    # If last_checked_count is None, this is the first check - just store state, don't notify
                    if media.last_checked_count is None:
                        self.logger.info(
                            f"Initial state for {media.title_romaji}: {total_count} available"
                        )
                        updates_to_make.append((media.id, float(total_count)))
                        continue

                    # Check if there are new releases since last check
                    last_known = media.last_checked_count

                    if total_count > last_known:
                        type_label = (
                            "episode"
                            if media.media_type == MediaType.ANIME
                            else "chapter"
                        )

                        self.logger.info(
                            f"New {type_label}(s) for {media.title_romaji}: "
                            f"was {last_known}, now {total_count}"
                        )

                        for number in range(int(last_known) + 1, int(total_count) + 1):
                            notifications.append(
                                {
                                    "number": float(number),
                                    "anilist_id": media.anilist_id,
                                    "title_romaji": media.title_romaji,
                                    "title_english": media.title_english,
                                    "media_type": media.media_type,
                                }
                            )

                        updates_to_make.append((media.id, float(total_count)))

                except Exception as e:
                    self.logger.error(f"Error checking {media.title_romaji}: {e}")
                    continue

            # Update database with new counts
            for media_id, new_count in updates_to_make:
                try:
                    await self.db.update_media_count(media_id, new_count)
                except Exception as e:
                    self.logger.error(
                        f"Failed to update count for media_id {media_id}: {e}"
                    )

            # Send notifications
            if notifications:
                try:
                    self.logger.info(
                        f"Found {len(notifications)} new releases, sending notifications"
                    )
                    self.notifier.notify_new_releases(notifications)
                except Exception as e:
                    self.logger.error(f"Failed to send notifications: {e}")
            else:
                self.logger.info("No new releases found")

            self.logger.info("Release check complete")

        except Exception as e:
            self.logger.error(f"Error during release check: {e}")
            if config.discord.notify_on_error:
                try:
                    self.notifier.send_error(f"Release check failed: {str(e)}")
                except Exception as notify_error:
                    self.logger.error(
                        f"Failed to send error notification: {notify_error}"
                    )
