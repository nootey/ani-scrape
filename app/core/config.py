from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator


class AnilistConfig(BaseModel):
    api_url: str = "https://graphql.anilist.co"
    username: str


class DatabaseConfig(BaseModel):
    path: str = "./storage/db/aniscrape.sqlite"
    auto_flush: bool = True

class DiscordConfig(BaseModel):
    webhook_url: str
    notify_on_error: bool = False

class SchedulerConfig(BaseModel):
    enabled: bool = True
    interval_hours: int = 1
    timezone: str = "Europe/Ljubljana"

    @field_validator("interval_hours")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        if v < 1:
            print(
                f"WARNING: Scheduler interval ({v} minutes) is too short. "
                f"Minimum interval is 1 hour. Using that instead."
            )
            return 1
        return v


class Config(BaseModel):
    anilist: AnilistConfig
    database: DatabaseConfig
    discord: DiscordConfig
    scheduler: SchedulerConfig

    @classmethod
    def from_yaml(cls, path: str | Path = "config.yaml") -> "Config":
        config_path = Path(path)

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls(**data)


# Load the configuration
config = Config.from_yaml()
