from typing import cast
from urllib.parse import urlparse

import requests


class APIError(Exception):
    """Custom exception for all API-related errors."""


class RepoClient:
    """UI-agnostic client for interacting with the deb2repo server."""

    def __init__(self, api_url: str, token: str):
        self.api_url: str = api_url.rstrip("/")
        self.headers: dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def add_repo(
        self, url: str, distro: str, package_override: str | None = None
    ) -> dict[str, object]:
        parsed_url = urlparse(url)
        path_parts = parsed_url.path.strip("/").split("/")

        if len(path_parts) != 2 or not parsed_url.netloc:
            raise ValueError(
                "Invalid repository URL. Expected format: https://<host>/<owner>/<repo>"
            )

        payload = {
            "host": parsed_url.netloc,
            "owner": path_parts[0],
            "repo_name": path_parts[1],
            "package_name": package_override if package_override else None,
            "distro": distro,
        }

        try:
            response = requests.post(
                f"{self.api_url}/api/repos/add",
                json=payload,
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            result = cast(dict[str, object], response.json())
            return result

        except requests.exceptions.HTTPError as e:
            if e.response is not None:
                if "application/json" in e.response.headers.get("Content-Type", ""):
                    error_json = cast(dict[str, object], e.response.json())
                    error_data = str(error_json.get("detail", str(e)))
                else:
                    error_data = str(e)

                status_code = e.response.status_code
            else:
                error_data = str(e)
                status_code = "Unknown"

            raise APIError(f"HTTP {status_code}: {error_data}")
        except requests.exceptions.RequestException as e:
            raise APIError(f"Network error: {e!s}")

    def list_repos(self) -> list[dict]:
        try:
            response = requests.get(
                f"{self.api_url}/api/repos/list", headers=self.headers, timeout=10
            )
            response.raise_for_status()
            return cast(list[dict], response.json())
        except requests.exceptions.HTTPError as e:
            if e.response is not None:
                if "application/json" in e.response.headers.get("Content-Type", ""):
                    error_json = cast(dict[str, object], e.response.json())
                    error_data = str(error_json.get("detail", str(e)))
                else:
                    error_data = str(e)

                status_code = e.response.status_code
            else:
                error_data = str(e)
                status_code = "Unknown"

            raise APIError(f"HTTP {status_code}: {error_data}")
        except requests.exceptions.RequestException as e:
            raise APIError(f"Network error: {e!s}")
