import argparse
import asyncio
import logging
import os
from logging import Logger
from pathlib import Path

from app.core.config import config
from app.core.logger import AppLogger
from app.core.database import DatabaseClient
from app.core.models import MediaType
from app.services.anilist_client import AniListClient
from app.services.scheduler import start_scheduler
from app.services.sync import AniListSync
from app.services.tracker import ReleaseTracker


class AniScrapeApp:
    def __init__(self, logger: Logger, db_url: str):
        self.logger = logger
        self.db = DatabaseClient(db_url, logger)
        self.client = AniListClient(logger)
        self.tracker = ReleaseTracker(logger, self.db)
        self.sync = AniListSync(logger, self.db)

    async def search_media(self):
        print("\n🔍 Anime/Manga search")
        print("=" * 50)

        keyword = input("Enter search keyword: ").strip()
        if not keyword:
            print("❌ No keyword provided!")
            return

        print("\nSearch in:")
        print("1. Anime")
        print("2. Manga")
        print("3. Both")

        choice = input("Choice (1/2/3): ").strip()

        media_type = None
        if choice == "1":
            media_type = "ANIME"
        elif choice == "2":
            media_type = "MANGA"

        print(f"\nSearching for '{keyword}'...\n")

        results = await self.client.search(keyword, media_type)

        if not results:
            print("❌ No results found!")
            return

        print(f"Found {len(results)} results:\n")
        print("=" * 80)

        for idx, result in enumerate(results, 1):
            title = result["title_english"] or result["title_romaji"]
            m_type = result["type"]

            if m_type == "ANIME":
                count = f"{result['episodes']} eps" if result["episodes"] else "? eps"
            else:
                count = f"{result['chapters']} chs" if result["chapters"] else "? chs"

            print(f"{idx}. [{m_type}] {title}")
            print(f"   Romaji: {result['title_romaji']}")
            print(f"   {count} | Status: {result['status']} | ID: {result['id']}")
            print("-" * 80)

        subscribe = input("\nSubscribe to any? (enter number or 'n'): ").strip()

        if subscribe.lower() != "n" and subscribe.isdigit():
            idx = int(subscribe) - 1
            if 0 <= idx < len(results):
                await self.subscribe_to_media(results[idx])

    async def subscribe_to_media(self, result: dict):
        media_type = MediaType.ANIME if result["type"] == "ANIME" else MediaType.MANGA

        _ = await self.db.add_or_update_media(
            anilist_id=result["id"],
            media_type=media_type,
            title_romaji=result["title_romaji"],
            title_english=result["title_english"],
        )

        print(f"\n✅ Subscribed to: {result['title_romaji']}")

    async def view_subscriptions(self):
        """View all subscribed media"""
        print("\n📋 Your Subscriptions")
        print("=" * 50)

        print("\nView:")
        print("1. Anime only")
        print("2. Manga only")
        print("3. Both")

        choice = input("Choice (1/2/3): ").strip()

        media_type = None
        if choice == "1":
            media_type = MediaType.ANIME
        elif choice == "2":
            media_type = MediaType.MANGA

        media_list = await self.db.get_all_tracked_media(media_type)

        if not media_list:
            print("\n❌ No subscriptions found!")
            return

        print(f"\nFound {len(media_list)} subscription(s):\n")
        print("=" * 80)

        for idx, media in enumerate(media_list, 1):
            title = media.title_english or media.title_romaji
            print(f"{idx}. [{media.media_type.value}] {title}")
            print(f"   Romaji: {media.title_romaji}")
            print(f"   AniList ID: {media.anilist_id}")

            if media.user_progress:
                type_str = (
                    "Episode" if media.media_type == MediaType.ANIME else "Chapter"
                )
                print(f"   Your progress: {type_str} {int(media.user_progress)}")

            if media.last_checked_count:
                type_str = (
                    "Episodes" if media.media_type == MediaType.ANIME else "Chapters"
                )
                print(f"   Available: {int(media.last_checked_count)} {type_str}")

            print(f"   Last updated: {media.last_updated_at}")
            print("-" * 80)

    async def show_menu(self):
        while True:
            print("\n" + "=" * 50)
            print("AniScrape - Anime & Manga notifier")
            print("=" * 50)
            print("\n1. Search & Subscribe")
            print("2. View Subscriptions")
            print("3. Exit")

            choice = input("\nChoice: ").strip()

            if choice == "1":
                await self.search_media()
            elif choice == "2":
                await self.view_subscriptions()
            elif choice == "3":
                print("\n👋 Exiting...")
                return
            else:
                print("\n❌ Invalid choice!")

    async def run_manual(self):
        self.logger.info("Starting in CLI mode")
        await self.db.create_models()
        await self.show_menu()
        await self.db.cleanup()

    async def run_automatic(self):
        self.logger.info("Starting in automatic mode")

        await self.db.create_models()

        self.logger.info("Syncing subscriptions from AniList...")
        await self.sync.sync_from_anilist()

        self.logger.info("Running initial release check...")
        await self.tracker.check_for_updates()

        self.logger.info("Starting scheduler...")
        await start_scheduler(self.logger)


async def main():
    parser = argparse.ArgumentParser(
        description="AniScrape - Anime & Manga Release Tracker"
    )
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Run in interactive manual mode (default: automatic mode)",
    )
    args = parser.parse_args()

    log_level = getattr(logging, config.logging.level.upper(), logging.INFO)
    logger = AppLogger(name="app", level=log_level).get_logger()
    logger.info("Starting ani-scrape")

    # Ensure database directory exists
    db_path = Path(config.database.path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Database directory ready: {db_path.parent}")

    db_url = f"sqlite+aiosqlite:///{config.database.path}"

    app = AniScrapeApp(logger, db_url)

    if args.manual:
        try:
            await app.run_manual()
        finally:
            os._exit(0)
    else:
        try:
            await app.run_automatic()
        finally:
            os._exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
