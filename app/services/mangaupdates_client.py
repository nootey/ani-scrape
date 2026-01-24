import aiohttp
from logging import Logger
from typing import Optional


class MangaUpdatesClient:
    def __init__(self, logger: Logger):
        self.logger = logger.getChild("mangaupdates")
        self.api_url = "https://api.mangaupdates.com/v1"

    async def search_by_title(self, title: str) -> Optional[int]:
        """Search for manga and return series ID"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/series/search",
                    json={"search": title, "perpage": 1},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        self.logger.warning(
                            f"Search failed with status {response.status}"
                        )
                        return None
                    data = await response.json()
                    results = data.get("results", [])
                    if results:
                        # Get first result that is type "Manga"
                        for result in results:
                            if result.get("record", {}).get("type") == "Manga":
                                return result["record"]["series_id"]
                    return None
        except Exception as e:
            self.logger.error(
                f"Exception during search for '{title}': {type(e).__name__}: {e}"
            )
            return None

    async def get_latest_chapter(self, series_id: int) -> Optional[float]:
        """Get latest chapter number for a series"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.api_url}/series/{series_id}",
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        self.logger.warning(
                            f"Get series failed with status {response.status}"
                        )
                        return None
                    data = await response.json()
                    latest = data.get("latest_chapter")
                    return float(latest) if latest else None
        except Exception as e:
            self.logger.error(
                f"Exception getting chapter for series {series_id}: {type(e).__name__}: {e}"
            )
            return None
