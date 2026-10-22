import json
import os
import sys
from pathlib import Path

from deb2repo_client.core import RepoClient

CONFIG_FILE = Path.home() / ".config" / "deb2repo" / "config.json"
DEFAULT_CONFIG = {"url": "http://127.0.0.1:8889", "token": ""}


def load_config() -> dict[str, str]:
    """Loads configuration using a cascase: Env Vars -> Config File."""
    api_url = os.getenv("REPO_API_URL")
    token = os.getenv("REPO_API_TOKEN")

    if not api_url or not token:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE) as f:
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
