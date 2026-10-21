import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, cast

from deb2repo_client.core import APIError, RepoClient
from deb2repo_client.exceptions import AmbiguousRepoError, RepoNotFoundError
from deb2repo_client.parser import build_master_parser
from deb2repo_client.utils import confirm_action, print_success

CONFIG_FILE = Path.home() / ".config" / "deb2repo" / "config.json"
DEFAULT_CONFIG = {"url": "", "token": ""}


def load_config() -> dict[str, str]:
    """Loads configuration using a cascase: Env Vars -> Config File."""
    api_url = os.getenv("REPO_API_URL")
    token = os.getenv("REPO_API_TOKEN")

    if not api_url or not token:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)

                    api_url = api_url or data.get("url") or "http://127.0.0.1:8889"
                    token = token or data.get("token")
            except json.JSONDecodeError:
                print(
                    f"Error: Malformed JSON configuration file at {CONFIG_FILE}",
                    file=sys.stderr,
                )
                sys.exit(1)
            except Exception as e:
                print(f"Unexpected error reading configuration: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            try:
                CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
                with open(CONFIG_FILE, "w") as f:
                    json.dump(DEFAULT_CONFIG, f, indent=4)
                print(
                    f"Created empty configuration file template at {CONFIG_FILE}. Please fill in the required fields.",
                    file=sys.stderr,
                )

            except Exception as e:
                print(f"Error creating configuration file: {e}", file=sys.stderr)

    if not api_url or not token:
        print("Fatal: Missing credentials.", file=sys.stderr)
        print(
            f"Set REPO_API_URL and REPO_API_TOKEN environment variables, or create {CONFIG_FILE} containing:",
            file=sys.stderr,
        )
        print(
            '{\n "url": "http://your-server-ip:8889", \n "token": "your-secure-token"\n}',
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
        repo = result_data.get("repo_name")

        stderr_msg = (
            f"Success: Added {owner}/{repo} to the build queue for '{args.distro}'"
        )
        stdout_msg = str(args.url)

        # Print the added url to stdout for scripting
        print_success(args, stderr_msg, stdout_msg)

    except (ValueError, APIError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


def cmd_remove(args: argparse.Namespace) -> None:
    client = get_client()
    try:

        try:
            repo, is_partial = client.resolve_repo(
                args.name,
                getattr(args, "distro", None),
                getattr(args, "host", None),
            )

            if is_partial:
                full_name = (
                    f"{repo.get('host')}/{repo.get('owner')}/{repo.get('repo_name')}"
                )

                if args.no_confirm:
                    print(
                        f"Notice: Using partial match '{full_name}' (--no-prompt passed).",
                        file=sys.stderr,
                    )
                else:
                    if not confirm_action(
                        f"Exact match for '{args.name}' not found. Did you mean '{full_name}'?"
                    ):
                        print("Operation aborted", file=sys.stderr)
                        sys.exit(1)

            repo_id = cast(int, repo.get("id"))
            result: dict[str, Any] = client.remove_repo(int(repo_id))
            result_data = cast(dict[str, Any], result.get("data", {}))

            host = result_data.get("host")
            owner = result_data.get("owner")
            repo = result_data.get("repo_name")
            removed_count = result_data.get("removed_files_count", 0)

            stderr_msg = f"Success: Removed {host}/{owner}/{repo} from tracking. {removed_count} \
                    associated files were deleted."
            stdout_msg = f"https://{host}/{owner}/{repo}"

            print_success(args, stderr_msg, stdout_msg)

        except RepoNotFoundError as error:
            print(f"Error: {error}", file=sys.stderr)
            sys.exit(1)
        except AmbiguousRepoError as error:
            print(f"Error: {error}", file=sys.stderr)
            print(
                "Use --distro and/or --host to disambiguate. Available options:",
                file=sys.stderr,
            )

            for r in error.matches:
                print(
                    f"  ID {r.get('id')}: {r.get('host')}/{r.get('owner')}/{r.get('repo_name')} \
                            (distro: {r.get('distro')})",
                    file=sys.stderr,
                )
            sys.exit(1)

    except (ValueError, APIError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)


def cmd_list(args: argparse.Namespace) -> None:
    client = get_client()
    try:
        repos = client.list_repos()
        if not repos:
            print("No packages are currently being tracked", file=sys.stderr)
            return
        print(
            f"{'PACKAGE':<25} {'LAST TAG':<15} {'DISTRO':<15} {'SOURCE':<40}",
            file=sys.stdout,
        )
        print("-" * 95, file=sys.stdout)
        for tracked_repo in repos:
            distro = tracked_repo.get("distro") or "N/A"
            packages = tracked_repo.get("packages") or ["Pending first sync"]
            last_tag = tracked_repo.get("last_tag") or "N/A"

            source = (
                f"{tracked_repo.get('host') or 'unknown'}/"
                f"{tracked_repo.get('owner') or 'unknown'}/"
                f"{tracked_repo.get('repo_name') or 'unknown'}"
            )

            for package_name in packages:
                print(
                    f"{package_name:<25} {last_tag:<15} {distro:<15} {source:<40}",
                    file=sys.stdout,
                )

    except APIError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_sync(args: argparse.Namespace) -> None:
    client = get_client()
    try:

        if args.name:
            try:
                repo, is_partial = client.resolve_repo(
                    args.name,
                    getattr(args, "distro", None),
                    getattr(args, "host", None),
                )

                if is_partial:
                    full_name = f"{repo.get('host')}/{repo.get('owner')}/{repo.get('repo_name')}"

                    if args.no_confirm:
                        print(
                            f"Notice: Using partial match '{full_name}' (--no-prompt passed).",
                            file=sys.stderr,
                        )
                    else:
                        if not confirm_action(
                            f"Exact match for '{args.name}' not found. Did you mean '{full_name}'?"
                        ):
                            print("Operation aborted", file=sys.stderr)
                            sys.exit(1)

                repo_id = cast(int, repo.get("id"))
                client.sync_repo(int(repo_id))

                stderr_msg = f"Sync triggered for {args.name}"
                stdout_msg = f"{args.name}"

                print_success(args, stderr_msg, stdout_msg)

            except RepoNotFoundError as error:
                print(f"Error: {error}", file=sys.stderr)
                sys.exit(1)
            except AmbiguousRepoError as error:
                print(f"Error: {error}", file=sys.stderr)
                print(
                    "Use --distro and/or --host to disambiguate. Available options:",
                    file=sys.stderr,
                )

                for r in error.matches:
                    print(
                        f"  ID {r.get('id')}: {r.get('host')}/{r.get('owner')}/{r.get('repo_name')} (distro: {r.get('distro')})",
                        file=sys.stderr,
                    )
                sys.exit(1)

        else:
            client.sync_all()
            print("Sync triggered for all repos", file=sys.stderr)

    except (ValueError, APIError) as error:
        print(f"Error: {error}", file=sys.stderr)
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

    print(
        f"Starting import of {len(lines)} repositories for '{args.distro}'...",
        file=sys.stderr,
    )

    try:
        result = client.import_repos(lines, args.distro)

    except (ValueError, APIError) as error:
        print(f"Import failed: {error}", file=sys.stderr)
        sys.exit(1)

    added = cast(list[dict[str, Any]], result.get("data", []))
    skipped = cast(list[dict[str, Any]], result.get("skipped", []))

    for repo in added:
        print(
            f"Queued {repo.get('owner', 'unknown')}/"
            f"{repo.get('repo_name', 'unknown')}",
            file=sys.stderr,
        )

    for repo in skipped:
        print(
            f"Skipped {repo.get('owner', 'unknown')} for "
            f"{repo.get('distro', 'unknown')}: "
            f"{repo.get('reason', 'unknown reason')}",
            file=sys.stderr,
        )

    stderr_msg = f"\nImport complete. Successfully queued {len(added)}/{len(lines)} repositories in one poll."
    stdout_msg = f"{len(added)}/{len(lines)}"

    print_success(args, stderr_msg, stdout_msg)


def main():

    parser = build_master_parser()

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
    elif args.command == "remove":
        cmd_remove(args)
    elif args.command == "sync":
        cmd_sync(args)


if __name__ == "__main__":
    main()
