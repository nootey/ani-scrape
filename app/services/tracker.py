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

            media_data = []
            for media in media_list:
                media_data.append({
                    "media_id": media.id,
                    "anilist_id": media.anilist_id,
                    "title_romaji": media.title_romaji,
                    "title_english": media.title_english,
                    "media_type": media.media_type,
                    "media_type_str": "ANIME" if media.media_type == MediaType.ANIME else "MANGA"
                })

            self.logger.info(f"Checking {len(media_data)} media for updates")

            new_releases = []

            for data in media_data:
                try:
                    media_info = await self.client.get_media_by_id(data["anilist_id"], data["media_type_str"])

                    if not media_info:
                        self.logger.warning(f"Could not fetch info for {data['title_romaji']}")
                        continue

                    if data["media_type"] == MediaType.ANIME:
                        total_count = media_info.get("episodes")
                    else:
                        total_count = media_info.get("chapters")

                    if not total_count:
                        self.logger.debug(f"No episode/chapter count for {data['title_romaji']}")
                        continue

                    latest_in_db = await self.db.get_latest_release_number(data["media_id"])

                    if latest_in_db is None:
                        type_label = "episode" if data["media_type"] == MediaType.ANIME else "chapter"
                        self.logger.info(
                            f"First check for {data['title_romaji']}, recording up to {type_label} {total_count}")
                        await self.db.add_release(data["media_id"], float(total_count))
                        continue

                    if total_count > latest_in_db:
                        self.logger.info(
                            f"New releases found for {data['title_romaji']}: {latest_in_db} -> {total_count}")

                        for number in range(int(latest_in_db) + 1, int(total_count) + 1):
                            release, is_new = await self.db.add_release(data["media_id"], float(number))

                            if is_new:
                                new_releases.append({
                                    "release_id": release.id,
                                    "number": float(number),
                                    "anilist_id": data["anilist_id"],
                                    "title_romaji": data["title_romaji"],
                                    "title_english": data["title_english"],
                                    "media_type": data["media_type"]
                                })

                except Exception as e:
                    self.logger.error(f"Error checking {data['title_romaji']}: {e}")
                    continue

            if new_releases:
                self.logger.info(f"Found {len(new_releases)} new releases, sending notifications")
                await self.send_notifications()
            else:
                self.logger.info("No new releases found")

            self.logger.info("Release check complete")

        except Exception as e:
            self.logger.error(f"Error during release check: {e}")
            if config.discord.notify_on_error:
                self.notifier.send_error(f"Release check failed: {str(e)}")

    async def send_notifications(self):
        try:
            releases = await self.db.get_unnotified_releases()

            if not releases:
                self.logger.info("No pending notifications")
                return

            self.logger.info(f"Sending notifications for {len(releases)} releases")

            notification_data = []
            release_ids = []

            for release in releases:
                release_ids.append(release.id)
                notification_data.append({
                    "release_id": release.id,
                    "number": release.number,
                    "anilist_id": release.media.anilist_id,
                    "title_romaji": release.media.title_romaji,
                    "title_english": release.media.title_english,
                    "media_type": release.media.media_type
                })

            self.notifier.notify_new_releases(notification_data)

            for release_id in release_ids:
                await self.db.mark_as_notified(release_id)

            self.logger.info("All notifications sent successfully")

        except Exception as e:
            self.logger.error(f"Error sending notifications: {e}")
            if config.discord.notify_on_error:
                self.notifier.send_error(f"Failed to send notifications: {str(e)}")