import os
import re

import feedparser
import requests
from typing import Any
from deb2repo.config import settings

VALID_DEB_PATTERN = re.compile(
    r"^(?!.*(-dbg|-dev)).*(amd64|x86_64|arm64|all).*\.deb$", re.IGNORECASE
)

UNSTABLE_PATTERN = re.compile(
    r"(rc|alpha|beta|dev|pre|nightly|test|snapshot)", re.IGNORECASE
)

KNOWN_CODENAMES = [
    "buster",
    "bullseye",
    "bookworm",
    "trixie",
    "sid",
    "forky",
    "jammy",
    "noble",
    "questing",
    "resolute",
]


def filter_assets(
    release_data: dict[str, Any], target_distro: str
) -> list[dict[str, Any]] | None:
    assets: list[dict[str, Any]] = release_data.get("assets", [])
    if target_distro not in KNOWN_CODENAMES:
        print(f"Warning: {target_distro} is not a known codename. Download aborted.")
        return []

    deb_assets = [
        asset
        for asset in assets
        if VALID_DEB_PATTERN.match(asset["name"])  # pyright: ignore[reportArgumentType]
    ]
    blacklisted_codenames = [dist for dist in KNOWN_CODENAMES if dist != target_distro]
    # fmt: off
    filtered_assets = [
        asset
        for asset in deb_assets
        if not any(bad_dist in asset["name"].lower() for bad_dist in blacklisted_codenames)  # pyright: ignore[reportArgumentType]
    ]
    # fmt: on
    return filtered_assets


def get_latest_tag(host: str, owner: str, name: str) -> str | None:
    base_url = f"https://{host}/{owner}/{name}/releases.atom"
    feed = feedparser.parse(base_url)

    if not feed.entries:
        print(f"No releases found for {host}/{owner}/{name}")
        return None
    for entry in feed.entries:
        tag = entry["link"].split("/")[-1]

        if not UNSTABLE_PATTERN.search(tag):
            print(f"Latest stable release tag: {tag}")
            return tag
    print(f"No stable releases found for {host}/{owner}/{name}")
    return None


def get_latest_deb(host: str, owner: str, name: str, distro: str) -> None:
    target_dir = os.path.join(settings.base_repo_path, "pool", distro, "main")

    tag = get_latest_tag(host, owner, name)
    if not tag:
        return

    api_url = f"https://api.{host}/repos/{owner}/{name}/releases/tags/{tag}"

    headers = {}

    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    response = requests.get(api_url, headers=headers)
    response.raise_for_status()
    release_data: dict[str, str] = response.json()

    deb_assets = filter_assets(release_data, distro)

    if not deb_assets:
        print(f"No .deb packages found in release {tag}")
        return

    for asset in deb_assets:

        download_url: str = asset["browser_download_url"]
        filename: str = asset["name"]

        filename = (
            filename.replace("x86_64", "amd64")
            .replace("armv8", "arm64")
            .replace("x86_32", "i386")
        )

        filename = re.sub(
            r"_(amd64|arm64|all)_(.*?)\.deb$",
            r"_\2_\1.deb",
            filename,
            flags=re.IGNORECASE,
        )

        file_path: str = os.path.join(target_dir, filename)

        os.makedirs(target_dir, exist_ok=True)

        print(f"Downloading {filename} to {target_dir}...")

        with requests.get(download_url, stream=True, headers=headers) as r:
            r.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    _ = f.write(chunk)

        print(f"Successfully downloaded {filename} to {file_path}")
