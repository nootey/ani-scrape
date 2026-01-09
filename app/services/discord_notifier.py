import time
from logging import Logger
from typing import List, Dict, Any

import requests

from app.core.config import config
from app.core.models import MediaType


class DiscordNotifier:
    def __init__(self, logger: Logger):
        self.logger = logger.getChild("discord")
        self.webhook_url = config.discord.webhook_url

    def notify_new_releases(self, releases: List[Dict[str, Any]]):
        if not self.webhook_url:
            self.logger.warning(
                "Discord webhook URL not configured, skipping notifications"
            )
            return

        if not releases:
            self.logger.info("No releases to notify")
            return

        self.logger.info(f"Sending {len(releases)} release notifications to Discord")

        batch_size = 10
        for i in range(0, len(releases), batch_size):
            batch = releases[i : i + batch_size]
            self._send_batch(batch)

            # Small delay between batches to avoid rate limits
            if i + batch_size < len(releases):
                time.sleep(1)

    def _send_batch(self, releases: List[Dict[str, Any]]):
        embeds = []

        for release in releases:
            media_type = release.get("media_type")
            title = release.get("title_english") or release.get("title_romaji")
            number = release.get("number")
            anilist_id = release.get("anilist_id")

            # Determine type string
            type_str = "Episode" if media_type == MediaType.ANIME else "Chapter"
            emoji = "📺" if media_type == MediaType.ANIME else "📚"

            embed = {
                "title": f"{emoji} New {type_str} Released!",
                "description": f"**{title}**\n{type_str} {number}",
                "color": 0x02A9FF,
                "url": f"https://anilist.co/{'anime' if media_type == MediaType.ANIME else 'manga'}/{anilist_id}",
                "footer": {"text": "AniScrape"},
            }

            embeds.append(embed)

        payload = {"embeds": embeds}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(self.webhook_url, json=payload, headers=headers)

            if response.status_code not in (200, 204):
                self.logger.warning(
                    f"Failed to send batch to Discord: {response.status_code} - {response.text}"
                )
            else:
                self.logger.info(
                    f"Discord batch sent successfully ({len(embeds)} releases)"
                )

        except Exception as e:
            self.logger.exception(
                f"Exception occurred while sending batch to Discord: {e}"
            )

    def send_error(self, error_message: str, details: str = None):
        if not self.webhook_url:
            return

        description = f"```\n{error_message}\n```"

        fields = []
        if details:
            fields.append({"name": "Details", "value": details, "inline": False})

        embed = {
            "title": "⚠️ AniScrape Error",
            "description": description,
            "color": 0xFF0000,  # Red
            "fields": fields,
            "footer": {"text": "AniScrape"},
        }

        payload = {"embeds": [embed]}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(self.webhook_url, json=payload, headers=headers)

            if response.status_code not in (200, 204):
                self.logger.warning(
                    f"Failed to send error to Discord: {response.status_code}"
                )
            else:
                self.logger.info("Discord error notification sent successfully")

        except Exception as e:
            self.logger.exception(
                f"Exception occurred while sending error to Discord: {e}"
            )
