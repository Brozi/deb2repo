import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, cast

from deb2repo_client.core import APIError, RepoClient

CONFIG_FILE = Path.home() / ".config" / "deb2repo" / "config.json"


def load_config() -> dict[str, str]:
    """Loads configuration using a cascase: Env Vars -> Config File."""
    api_url = os.getenv("REPO_API_URL")
    token = os.getenv("REPO_API_TOKEN")

    if not api_url or not token:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)

                    api_url = api_url or data.get("url")
                    token = token or data.get("token")
            except json.JSONDecodeError:
                print(f"Error: Malformed JSON configuration file at {CONFIG_FILE}")
                sys.exit(1)
            except Exception as e:
                print(f"Unexpected error reading configuration: {e}", file=sys.stderr)
                sys.exit(1)

    if not api_url or not token:
        print("Fatal: Missing credentials.", file=sys.stderr)
        print(
            f"Set REPO_API_URL and REPO_API_TOKEN environment variables, or create {CONFIG_FILE} containing:",
            file=sys.stderr,
        )
        print(
            '{\n "url": "http://your-server-ip:8000", \n "token": "your-secure-token"\n}',
            file=sys.stderr,
        )
        sys.exit(1)

    return {"url": api_url, "token": token}


def get_client() -> RepoClient:
    """Instantiates the UI-agnostic client using environment configurations"""
    config = load_config()

    return RepoClient(config["url"], config["token"])


def cmd_add(args: argparse.Namespace) -> None:
    client = get_client()
    try:
        result: dict[str, Any] = client.add_repo(args.url, args.distro, args.package)
        result_data = cast(dict[str, Any], result.get("data", {}))
        owner = result_data.get("owner")
        repo = result_data.get("repo")
        print(f"Success: Added {owner}/{repo} to the build queue for '{args.distro}'")
    except (ValueError, APIError) as e:
        print(f"Erorr: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_list(args: argparse.Namespace) -> None:
    client = get_client()
    try:
        repos = client.list_repos()
        if not repos:
            print("No packages are currently being tracked")
            return
        print(f"{'PACKAGE':<25} {'DISTRO':<15} {'SOURCE':<40}")
        print("-" * 80)
        for tracked_repo in repos:
            packages = tracked_repo.get("packages") or []
            package_display = ", ".join(packages) if packages else "Pending first sync"
            distro = tracked_repo.get("distro") or "N/A"
            source = (
                f"{tracked_repo.get('host') or 'unknown'}/"
                f"{tracked_repo.get('owner') or 'unknown'}/"
                f"{tracked_repo.get('repo_name') or 'unknown'}"
            )

            print(f"{package_display:<25} {distro:<15} {source:<40}")

    except APIError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_import(args: argparse.Namespace) -> None:
    client: RepoClient = get_client()
    filepath = Path(args.file)

    if not filepath.exists() or not filepath.is_file():
        print(f"Fatal: Cannot read file '{filepath}'", file=sys.stderr)
        sys.exit(1)

    with open(filepath, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines:
        print("Fatal: The provided file is empty.", file=sys.stderr)
        sys.exit(1)
    print(f"Starting import of {len(lines)} repositories for '{args.distro}'...")

    success_count = 0
    for i, url in enumerate(lines, start=1):
        try:
            result: dict[str, Any] = client.add_repo(url, args.distro)
            result_data = cast(dict[str, Any], result.get("data", {}))

            owner = result_data.get("owner", "unknown")
            repo = result_data.get("repo_name", "unknown")

            print(f"[{i}/{len(lines)}] Success: Queued {owner}/{repo}")
            success_count += 1
        except (ValueError, APIError) as e:
            print(f"[{i}/{len(lines)}] Error adding '{url}': {e}", file=sys.stderr)

    print(
        f"\nImport complete. Successfully queued {success_count}/{len(lines)} repositories."
    )


def main():
    parser = argparse.ArgumentParser(description="deb2repo admin cli client")

    parser.add_argument(
        "-t", "--tui", action="store_true", help="Launch the TUI client"
    )

    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser(
        "add", help="Add a new repo to the tracking database"
    )
    add_parser.add_argument("url", help="Repository URL")
    add_parser.add_argument("-d", "--distro", required=True, help="Target distribution")
    add_parser.add_argument(
        "-p",
        "--package",
        help="Override package name (default: inferred from the .deb package",
    )
    add_parser.set_defaults(func=cmd_add)

    import_parser = subparsers.add_parser(
        "import", help="Bulk import repositories from a text file"
    )
    import_parser.add_argument(
        "file", help="Path to the text file containing repository URLs"
    )
    import_parser.add_argument(
        "-d",
        "--distro",
        required=True,
        help="Target distribution for all imported repositories.",
    )
    import_parser.set_defaults(func=cmd_import)

    list_parser = subparsers.add_parser("list", help="List tracked repos")

    list_parser.add_argument(
        "-s",
        "--scripting",
        help="Output in a scripting-friendly format",
        action="store_true",
    )

    args = parser.parse_args()

    if args.tui:
        from deb2repo_client.tui import main as tui_main

        sys.exit(tui_main())

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "add":
        cmd_add(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "import":
        cmd_import(args)


if __name__ == "__main__":
    main()
