import re

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    github_token: str | None = None
    gpg_key_id: str
    repo_origin: str = "My Custom Repo"
    base_repo_path: str = "/app/repo"
    db_url: str = "sqlite:////app/state/repo_state.db"
    keep_count: int = 2
    hosted_archs: str = "amd64, arm64, i386, all"
    known_codenames: str = (
        "buster,bullseye,bookworm,trixie,sid,forky,jammy,noble,questing,resolute"
    )

    blacklisted_keywords: str = "rc,alpha,beta,dev,pre,nightly,test,snapshot"
    asset_exclude_keywords: str = "termux,musl"
    polling_interval: str | dict[str, int] = Field(default={"minutes": 15})
    api_token: str | None = None

    @field_validator("polling_interval", mode="before")
    @classmethod
    def parse_polling_interval(cls, value: str | dict[str, int]) -> dict[str, int]:
        if isinstance(value, dict):
            return value

        value = value.lower().replace(" ", "")
        if not value:
            raise ValueError("polling_interval cannot be empty")

        pattern = re.compile(r"(\d+)([mhd])")
        matches: list[str] = pattern.findall(value)

        if not matches:
            raise ValueError(
                "Invalid interval format. Use formats like '10h5m', '1d12h', or '15m'."
            )

        if pattern.sub("", value):
            raise ValueError(
                f"Invalid characters in interval string: '{value}'. Allowed units are 'm', 'h', 'd'."
            )

        unit_mapping = {"m": "minutes", "h": "hours", "d": "days"}

        parsed_intervals: dict[str, int] = {}
        for amount_str, unit_char in matches:
            unit = unit_mapping[unit_char]
            parsed_intervals[unit] = parsed_intervals.get(unit, 0) + int(amount_str)

        return parsed_intervals

    #fmt: off

    model_config  = SettingsConfigDict(  # pyright: ignore[reportUnannotatedClassAttribute]
        env_file=".env", env_file_encoding="utf-8"
    )
    #fmt: on


settings = Settings()  # pyright: ignore[reportCallIssue]
