import argparse
import asyncio
import os
import sys
from logging import Logger
from pathlib import Path

from app.core.config import config
from app.core.logger import AppLogger
from app.core.database import DatabaseClient
from app.core.models import MediaType
from app.services.anilist_client import AniListClient
from app.services.scheduler import start_scheduler
from app.services.tracker import ReleaseTracker


class AniScrapeApp:
    def __init__(self, logger: Logger, db_url: str):
        self.logger = logger
        self.db = DatabaseClient(db_url, logger)
        self.client = AniListClient(logger)
        self.tracker = ReleaseTracker(logger, self.db)

    async def search_media(self):
        print("\n Anime/Manga search")
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
                count = f"{result['episodes']} eps" if result['episodes'] else "? eps"
            else:
                count = f"{result['chapters']} chs" if result['chapters'] else "? chs"

            print(f"{idx}. [{m_type}] {title}")
            print(f"   Romaji: {result['title_romaji']}")
            print(f"   {count} | Status: {result['status']} | ID: {result['id']}")
            print("-" * 80)

        subscribe = input("\nSubscribe to any? (enter number or 'n'): ").strip()

        if subscribe.lower() != 'n' and subscribe.isdigit():
            idx = int(subscribe) - 1
            if 0 <= idx < len(results):
                await self.subscribe_to_media(results[idx])

    async def subscribe_to_media(self, result: dict):
        media_type = MediaType.ANIME if result["type"] == "ANIME" else MediaType.MANGA

        _ = await self.db.add_or_update_media(
            anilist_id=result["id"],
            media_type=media_type,
            title_romaji=result["title_romaji"],
            title_english=result["title_english"]
        )

        print(f"\nSubscribed to: {result['title_romaji']}")

    async def view_subscriptions(self):
        """View all subscribed media"""
        print("\nYour Subscriptions")
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
            print(f"   Last updated: {media.last_updated_at}")

            latest = await self.db.get_latest_release_number(media.id)
            if latest:
                type_str = "Episode" if media.media_type == MediaType.ANIME else "Chapter"
                print(f"   Latest: {type_str} {latest}")

            print("-" * 80)

    async def show_menu(self):
        while True:
            print("\n" + "=" * 50)
            print("AniScrape - Anime & Manga notifier")
            print("=" * 50)
            print("\n1. Search & Subscribe")
            print("2. View Subscriptions")
            print("3. Test Notifications")
            print("4. Exit")

            choice = input("\nChoice: ").strip()

            if choice == "1":
                await self.search_media()
            elif choice == "2":
                await self.view_subscriptions()
            elif choice == "3":
                await self.test_notification()
            elif choice == "4":
                print("\n Exiting ...")
                return
            else:
                print("\n❌ Invalid choice!")

    async def run_cli(self):
        self.logger.info("Starting in CLI mode")
        await self.db.create_models()
        await self.show_menu()
        await self.db.cleanup()

    async def run_daemon(self):
        """Run in daemon mode with scheduler"""
        self.logger.info("Starting in daemon mode")
        await self.db.create_models()

        self.logger.info("Running initial release check...")
        await self.tracker.check_for_updates()

        # Start scheduler if enabled
        if config.scheduler.enabled:
            self.logger.info("Starting scheduler...")
            await start_scheduler(self.logger)
        else:
            self.logger.info("Scheduler disabled, exiting after initial check")
            await self.db.cleanup()

    async def test_notification(self):
        """Test notifications by rolling back last release"""
        print("\n🧪 Testing Notification System")
        print("=" * 50)

        media_list = await self.db.get_all_tracked_media()

        if not media_list:
            print("❌ No subscriptions found! Subscribe to something first.")
            return

        print("\nYour subscriptions:")
        for idx, media in enumerate(media_list, 1):
            latest = await self.db.get_latest_release_number(media.id)
            type_str = "Episode" if media.media_type == MediaType.ANIME else "Chapter"
            print(f"{idx}. {media.title_romaji} - Latest: {type_str} {latest if latest else 'None'}")

        choice = input("\nWhich one to test? (enter number): ").strip()

        if not choice.isdigit():
            print("❌ Invalid choice!")
            return

        idx = int(choice) - 1
        if idx < 0 or idx >= len(media_list):
            print("❌ Invalid choice!")
            return

        media = media_list[idx]
        latest = await self.db.get_latest_release_number(media.id)

        # If no releases yet, run tracker first to establish baseline
        if not latest:
            print(f"\n⚠️  No releases tracked yet for {media.title_romaji}")
            print("Running initial tracker check to establish baseline...\n")
            await self.tracker.check_for_updates()

            # Check again
            latest = await self.db.get_latest_release_number(media.id)
            if not latest:
                print("❌ Could not fetch release info from AniList!")
                print("This media might not have episode/chapter count available yet.")
                print("\n💡 Try subscribing to a completed or well-established series for testing.")
                print("   Example: 'One Piece' manga has chapter counts available.")
                return

            print(f"✅ Baseline established at {latest}")

        # Manually add a test release if we have a baseline
        type_str = "episode" if media.media_type == MediaType.ANIME else "chapter"

        # Create a fake "new" release
        test_number = latest + 1
        release, is_new = await self.db.add_release(media.id, test_number)

        if is_new:
            print(f"\n✅ Created test release: {type_str} {test_number}")
            print("Now sending notification...\n")

            # Send notification for this release
            await self.tracker.send_notifications()

            print("\n✅ Test complete! Check your Discord for the notification.")
        else:
            print(f"❌ Test release {test_number} already exists!")

async def main():

    parser = argparse.ArgumentParser(description="AniScrape - Anime & Manga Release Tracker")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run in interactive CLI mode (default: daemon mode)"
    )
    args = parser.parse_args()

    logger = AppLogger(name="app").get_logger()
    logger.info("Starting ani-scrape")

    # Ensure database directory exists
    db_path = Path(config.database.path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Database directory ready: {db_path.parent}")

    db_url = f"sqlite+aiosqlite:///{config.database.path}"

    app = AniScrapeApp(logger, db_url)

    if args.cli:
        await app.run_cli()
        os._exit(0)
    else:
        await app.run_daemon()


if __name__ == "__main__":
    asyncio.run(main())