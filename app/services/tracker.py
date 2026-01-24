from logging import Logger

from app.core.database import DatabaseClient
from app.core.models import MediaType
from app.services.anilist_client import AniListClient
from app.services.discord_notifier import DiscordNotifier
from app.core.config import config


class ReleaseTracker:
    def __init__(self, logger: Logger, db: DatabaseClient):
        self.logger = logger.getChild("tracker")
        self.db = db
        self.client = AniListClient(logger)
        self.notifier = DiscordNotifier(logger)

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
                    media_type_str = (
                        "ANIME" if media.media_type == MediaType.ANIME else "MANGA"
                    )
                    media_info = await self.client.get_media_by_id(
                        media.anilist_id, media_type_str
                    )

                    if not media_info:
                        self.logger.warning(
                            f"Could not fetch info for {media.title_romaji}"
                        )
                        continue

                    total_count = media_info.get(
                        "episodes"
                        if media.media_type == MediaType.ANIME
                        else "chapters"
                    )

                    if not total_count:
                        self.logger.warning(
                            f"No count available for {media.title_romaji}"
                        )
                        continue

                    # Check if there are new releases since last check
                    last_known = media.last_checked_count or media.user_progress

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

                        # Notify about each new release
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

            for media_id, new_count in updates_to_make:
                await self.db.update_media_count(media_id, new_count)

            if notifications:
                self.logger.info(
                    f"Found {len(notifications)} new releases, sending notifications"
                )
                self.notifier.notify_new_releases(notifications)
            else:
                self.logger.info("No new releases found")

            self.logger.info("Release check complete")

        except Exception as e:
            self.logger.error(f"Error during release check: {e}")
            if config.discord.notify_on_error:
                self.notifier.send_error(f"Release check failed: {str(e)}")
