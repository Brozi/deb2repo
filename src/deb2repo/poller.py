import os
import re

import feedparser
import requests

VALID_DEB_PATTERN = re.compile(
    r"^(?!.*(-dbg|-dev)).*(amd64|x86_64|all).*\.deb$", re.IGNORECASE
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


def filter_assets(release_data: dict[str, str], target_distro: str) -> list[str] | None:
    assets = release_data.get("assets", [])
    if target_distro not in KNOWN_CODENAMES:
        print(f"Warning: {target_distro} is not a known codename. Download aborted.")
        return

    deb_assets_pre_filter = [
        asset
        for asset in assets
        if VALID_DEB_PATTERN.match(asset["name"])  # pyright: ignore[reportArgumentType]
    ]
    assets = deb_assets_pre_filter

    if len(assets) > 1:
        blacklisted_codenames = [
            dist for dist in KNOWN_CODENAMES if dist != target_distro
        ]
        # fmt: off
        deb_assets = [
            asset
            for asset in assets
            if not any(bad_dist in asset["name"].lower() for bad_dist in blacklisted_codenames)  # pyright: ignore[reportArgumentType]
        ]
        # fmt: on
        return deb_assets
    else:
        return assets


def get_latest_deb(
    host: str, owner: str, repo: str, distro: str, target_dir: str = "./repo/pool/main/"
):

    base_url = f"https://{host}.com/{owner}/{repo}/releases.atom"
    feed = feedparser.parse(base_url)

    if not feed.entries:
        print(f"No releases found for {host}/{owner}/{repo}")
        return
    latest_entry = feed.entries[0]
    tag = latest_entry["link"].split("/")[-1]
    print(f"Latest release tag: {tag}")

    api_url = f"https://api.{host}.com/repos/{owner}/{repo}/releases/tags/{tag}"
    response = requests.get(api_url)
    response.raise_for_status()
    release_data: dict[str, str] = response.json()

    deb_assets = filter_assets(release_data, distro)

    if not deb_assets:
        print(f"No .deb packages found in release {tag}")
        return

    target_asset = deb_assets[0]
    download_url: str = target_asset["browser_download_url"]
    filename: str = target_asset["name"]
    file_path = os.path.join(target_dir, filename)

    os.makedirs(target_dir, exist_ok=True)

    print(f"Downloading {filename} from {download_url}...")

    with requests.get(download_url, stream=True) as r:
        r.raise_for_status()
        with open(file_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                _ = f.write(chunk)

    print(f"Successfully downloaded {filename} to {file_path}")
