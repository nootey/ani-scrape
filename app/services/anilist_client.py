import asyncio
from logging import Logger
from typing import List, Dict, Any, Optional

import aiohttp

from app.core.config import config


class AniListClient:
    def __init__(self, logger: Logger):
        self.logger = logger.getChild("anilist")
        self.api_url = config.anilist.api_url

    async def _query(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.api_url,
                json={"query": query, "variables": variables or {}},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 429:
                    self.logger.warning(
                        "Rate limited by AniList, waiting 10 seconds..."
                    )
                    await asyncio.sleep(10)
                    return await self._query(query, variables)

                if response.status != 200:
                    self.logger.error(f"AniList API error: {response.status}")
                    return {}

                data = await response.json()

                if "errors" in data:
                    self.logger.error(f"GraphQL errors: {data['errors']}")
                    return {}

                await asyncio.sleep(0.5)

                return data.get("data", {})

    async def search(
        self, keyword: str, media_type: str = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        query = """
        query ($search: String, $type: MediaType, $perPage: Int) {
            Page(perPage: $perPage) {
                media(search: $search, type: $type, sort: POPULARITY_DESC) {
                    id
                    type
                    title {
                        romaji
                        english
                    }
                    episodes
                    chapters
                    status
                    siteUrl
                }
            }
        }
        """

        variables = {"search": keyword, "type": media_type, "perPage": limit}

        data = await self._query(query, variables)

        results = []
        media_list = data.get("Page", {}).get("media", [])

        for media in media_list:
            results.append(
                {
                    "id": media["id"],
                    "type": media["type"],
                    "title_romaji": media["title"]["romaji"],
                    "title_english": media["title"].get("english"),
                    "episodes": media.get("episodes"),
                    "chapters": media.get("chapters"),
                    "status": media.get("status"),
                    "url": media.get("siteUrl"),
                }
            )

        return results

    async def get_media_by_id(
        self, media_id: int, media_type: str
    ) -> Optional[Dict[str, Any]]:
        query = """
        query ($id: Int, $type: MediaType) {
            Media(id: $id, type: $type) {
                id
                type
                title {
                    romaji
                    english
                }
                episodes
                chapters
                status
                siteUrl
            }
        }
        """

        variables = {"id": media_id, "type": media_type}

        data = await self._query(query, variables)

        if data.get("Media"):
            media = data["Media"]
            return {
                "anilist_id": media.get("id"),
                "type": media.get("type"),
                "title_romaji": media.get("title", {}).get("romaji"),
                "title_english": media.get("title", {}).get("english"),
                "episodes": media.get("episodes"),
                "chapters": media.get("chapters"),
                "status": media.get("status"),
                "url": media.get("siteUrl"),
            }

        return None

    async def get_user_anime_list(
        self, username: str, status: str = "CURRENT"
    ) -> List[Dict[str, Any]]:
        """Get user's anime list"""
        query = """
        query ($username: String, $status: MediaListStatus) {
            MediaListCollection(userName: $username, type: ANIME, status: $status) {
                lists {
                    entries {
                        progress
                        media {
                            id
                            title {
                                romaji
                                english
                            }
                            episodes
                            status
                        }
                    }
                }
            }
        }
        """

        variables = {"username": username, "status": status}
        data = await self._query(query, variables)

        anime_list = []
        if data.get("MediaListCollection") and data["MediaListCollection"].get("lists"):
            for list_group in data["MediaListCollection"]["lists"]:
                for entry in list_group.get("entries", []):
                    media = entry.get("media", {})
                    anime_list.append(
                        {
                            "id": media.get("id"),
                            "type": "ANIME",
                            "title_romaji": media.get("title", {}).get("romaji"),
                            "title_english": media.get("title", {}).get("english"),
                            "episodes": media.get("episodes"),
                            "status": media.get("status"),
                            "progress": entry.get("progress", 0),  # ADD THIS LINE
                        }
                    )

        return anime_list

    async def get_user_manga_list(
        self, username: str, status: str = "CURRENT"
    ) -> List[Dict[str, Any]]:
        """Get user's manga list"""
        query = """
        query ($username: String, $status: MediaListStatus) {
            MediaListCollection(userName: $username, type: MANGA, status: $status) {
                lists {
                    entries {
                        progress
                        media {
                            id
                            title {
                                romaji
                                english
                            }
                            chapters
                            status
                        }
                    }
                }
            }
        }
        """

        variables = {"username": username, "status": status}
        data = await self._query(query, variables)

        manga_list = []
        if data.get("MediaListCollection") and data["MediaListCollection"].get("lists"):
            for list_group in data["MediaListCollection"]["lists"]:
                for entry in list_group.get("entries", []):
                    media = entry.get("media", {})
                    manga_list.append(
                        {
                            "id": media.get("id"),
                            "type": "MANGA",
                            "title_romaji": media.get("title", {}).get("romaji"),
                            "title_english": media.get("title", {}).get("english"),
                            "chapters": media.get("chapters"),
                            "status": media.get("status"),
                            "progress": entry.get("progress", 0),  # ADD THIS LINE
                        }
                    )

        return manga_list
