import argparse
import json
import os
import sys
from pathlib import Path

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
        result = client.add_repo(args.url, args.distro, args.package)
        print(
            f"Success: Added {result.get('owner')}/{result.get('repo')} to the build queue for '{args.distro}'"
        )
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
        for t in repos:
            source = f"{t.get('host')}/{t.get('owner')}/{t.get('package_name')}"
            print(
                f"{t.get('package_name', 'N/A'):<25} {t.get('distro', 'N/A'):<15} {source:<40}"
            )
    except APIError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="deb2repo admin cli client")

    parser.add_argument(
        "-t", "--tui", action="store_true", help="Launch the TUI client"
    )

    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser(
        "add", help="Add a new repo to the tracking database"
    )
    add_parser.add_argument("url")
    add_parser.add_argument("-d", "--distro", required=True)
    add_parser.add_argument("-p", "--package")

    subparsers.add_parser("list", help="List tracked repos")

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


if __name__ == "__main__":
    main()
