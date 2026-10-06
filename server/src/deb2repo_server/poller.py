import os
import re
from pathlib import Path
from typing import Any

import feedparser
import requests

from deb2repo_server.config import settings
from deb2repo_server.parser import extract_package_name
from deb2repo_server.pruner import prune_obsolete_pkgs

ARCH_MATRIX = {
    # 1. Universal / Scripts (Checked first to bypass hardware specifics)
    "noarch": "all",
    "universal": "all",
    "all": "all",
    # 2. x86 / 64-bit (Must precede x86 32-bit to prevent false positive matching)
    "x86_64": "amd64",
    "amd64": "amd64",
    "x64": "amd64",
    "64bit": "amd64",
    # 3. x86 / 32-bit
    "x86_32": "i386",
    "i386": "i386",
    "i486": "i386",
    "i586": "i386",
    "i686": "i386",
    "32bit": "i386",
    "x86": "i386",  # Left at the bottom of the x86 block as a dangerous catch-all
    # 4. ARM / 64-bit
    "aarch64": "arm64",
    "arm64": "arm64",
    "armv8": "arm64",
    # 5. ARM / 32-bit (Hard Float)
    "armhf": "armhf",
    "armv7l": "armhf",
    "armv7": "armhf",
    # 6. ARM / 32-bit (Soft Float / Older Embedded)
    "armel": "armel",
    "armv6l": "armel",
    "armv6": "armel",
    # 7. RISC-V
    "riscv64": "riscv64",
    "rv64": "riscv64",
    # 8. PowerPC (Little Endian)
    "ppc64le": "ppc64el",
    "ppc64el": "ppc64el",
    # 9. IBM System z
    "s390x": "s390x",
    # 10. MIPS (Little Endian, 64-bit)
    "mips64le": "mips64el",
    "mips64el": "mips64el",
}


def get_unstable_pattern() -> re.Pattern[str]:
    raw_keywords = settings.unstable_keywords
    keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
    regex_string = "|".join(keywords)
    return re.compile(rf"({regex_string})", re.IGNORECASE)


def get_known_codenames() -> list[str]:
    raw_codenames = settings.known_codenames
    return [c.strip().lower() for c in raw_codenames.split(",") if c.strip()]


def filter_assets(
    release_data: dict[str, Any], target_distro: str, package_name: str | None
) -> list[dict[str, Any]] | None:
    assets: list[dict[str, Any]] = release_data.get("assets", [])
    known_codenames = get_known_codenames()
    if target_distro not in known_codenames:
        print(f"Warning: {target_distro} is not a known codename. Download aborted.")
        return []

    raw_hosted = settings.hosted_archs
    hosted_archs = [a.strip() for a in raw_hosted.split(",")]

    unstable_pattern = get_unstable_pattern()
    blacklisted_codenames = [dist for dist in known_codenames if dist != target_distro]
    valid_downloads = []

    for asset in assets:
        filename = asset.get("name", "").lower()

        if not filename.endswith(".deb"):
            continue

        if unstable_pattern.search(filename):
            print(f"Skipping unstable package: {filename}")
            continue

        if any(bad_dist in filename for bad_dist in blacklisted_codenames):
            print(f"Skipping package for other distros: {filename}")
            continue

        if package_name and package_name.lower() not in filename:
            continue

        for search_term, debian_arch in ARCH_MATRIX.items():
            if search_term in filename:
                if debian_arch in hosted_archs:
                    asset["debian_arch"] = debian_arch
                    valid_downloads.append(asset)
                break
    return valid_downloads


def get_latest_tag(host: str, owner: str, name: str) -> str | None:
    base_url = f"https://{host}/{owner}/{name}/releases.atom"
    feed = feedparser.parse(base_url)

    if not feed.entries:
        print(f"No releases found for {host}/{owner}/{name}")
        return None

    unstable_pattern = get_unstable_pattern()

    for entry in feed.entries:
        tag = entry["link"].split("/")[-1]

        if not unstable_pattern.search(tag):
            print(f"Latest stable release tag: {tag}")
            return tag
    print(f"No stable releases found for {host}/{owner}/{name}")
    return None


def get_latest_deb(
    host: str, owner: str, repo_name: str, distro: str, package_name: str | None
) -> list[Path] | None:
    target_dir = os.path.join(settings.base_repo_path, "pool", distro, "main")

    tag = get_latest_tag(host, owner, repo_name)
    if not tag:
        return

    api_url = f"https://api.{host}/repos/{owner}/{repo_name}/releases/tags/{tag}"

    headers: dict[str, str] = {}

    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    response = requests.get(api_url, headers=headers)
    response.raise_for_status()
    release_data: dict[str, str] = response.json()

    deb_assets: list[dict[str, str]] | None = filter_assets(
        release_data, distro, package_name=package_name
    )

    if not deb_assets:
        print(f"No .deb packages found in release {tag}")
        return

    os.makedirs(target_dir, exist_ok=True)
    clean_version = tag.lstrip("v")
    downloaded_paths: list[Path] = []

    for asset in deb_assets:

        download_url: str = asset["browser_download_url"]
        original_filename: str = asset["name"]
        debian_arch: str = asset.get("debian_arch", "all")

        tmp_filename = f".tmp_{original_filename}"
        tmp_filepath = os.path.join(target_dir, tmp_filename)

        print(f"Downloading {original_filename} as to {target_dir}...")

        with requests.get(download_url, stream=True, headers=headers) as r:
            r.raise_for_status()
            with open(tmp_filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    _ = f.write(chunk)
        try:
            true_pkg_name = extract_package_name(tmp_filepath)
        except Exception as e:  # noqa: BLE001
            print(
                f"Failed to extract metadata from {original_filename}. Falling back to repo name '{repo_name}'. Error: {e}"
            )
            true_pkg_name = repo_name

        final_filename = f"{true_pkg_name}_{clean_version}_{debian_arch}.deb"
        final_filepath = os.path.join(target_dir, final_filename)

        os.replace(tmp_filepath, final_filepath)

        print(f"Successfully processed and saved {final_filename} to {target_dir}.")

        downloaded_paths.append(Path(final_filepath))

    print("Running garbage collection...")
    prune_obsolete_pkgs(target_dir, settings.keep_count)

    return downloaded_paths
