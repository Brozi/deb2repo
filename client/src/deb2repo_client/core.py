from typing import Any, cast
from urllib.parse import urlparse

import requests

from deb2repo_client.exceptions import AmbiguousRepoError, RepoNotFoundError


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

    def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> Any:
        """Sends an HTTP request to the API and returns the parsed JSON response.
        Handles all error wrapping so individual methods stay clean."""
        url = f"{self.api_url}{path}"
        try:
            response = requests.request(
                method, url, headers=self.headers, json=json, timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as error:
            raise self._api_error(error) from error
        except requests.exceptions.RequestException as error:
            raise APIError(f"Network error: {error!s}") from error

    def resolve_repo(
        self, name: str, distro: str | None, host: str | None
    ) -> tuple[dict[str, object], bool]:
        """
        Resolves a human friendly name like 'bat' or 'sharkdp/bat' to a single tracked repo.
        Raises ValueError if the name is ambiguous or not found.
        """

        repos = self.list_repos()

        if "/" in name:
            parts = name.strip("/").split("/")
            owner, repo_name = parts[-2], parts[-1]
            exact_matches = [
                r
                for r in repos
                if r.get("owner") == owner and r.get("repo_name") == repo_name
            ]
            partial_matches = [
                r
                for r in repos
                if r.get("owner") == owner and repo_name in str(r.get("repo_name", ""))
            ]

        else:
            repo_name = name
            exact_matches = [r for r in repos if r.get("repo_name") == repo_name]
            partial_matches = [
                r for r in repos if repo_name in str(r.get("repo_name", ""))
            ]

        if exact_matches:
            matches = exact_matches
            is_partial = False
        else:
            matches = partial_matches
            is_partial = True

        if host and len(matches) > 1:
            matches = [r for r in matches if r.get("host") == host]

        if distro and len(matches) > 1:
            matches = [r for r in matches if r.get("distro") == distro]

        if len(matches) == 0:
            raise RepoNotFoundError(name)

        if len(matches) > 1:

            raise AmbiguousRepoError(name, matches)

        return cast(dict[str, object], matches[0]), is_partial

    def add_repo(
        self, url: str, distro: str, package_override: str | None = None
    ) -> dict[str, object]:

        payload = self._build_repo_payload(url, distro, package_override)

        return cast(
            dict[str, object], self._request("POST", "/api/repos/add", json=payload)
        )

    def remove_repo(self, repo_id) -> dict[str, object]:
        return cast(
            dict[str, object], self._request("DELETE", f"/api/repos/remove/{repo_id}")
        )

    def import_repos(self, urls: list[str], distro: str) -> dict[str, object]:
        """Mass import repos from a file"""
        payload = {"repos": [self._build_repo_payload(url, distro) for url in urls]}
        return cast(
            dict[str, object], self._request("POST", "/api/repos/import", json=payload)
        )

    def sync_all(self) -> dict[str, object]:
        return cast(dict[str, object], self._request("POST", "/api/repos/sync"))

    def sync_repo(self, repo_id) -> dict[str, object]:
        return cast(
            dict[str, object], self._request("POST", f"/api/repos/sync/{repo_id}")
        )

    def list_repos(self) -> list[dict]:
        return cast(list[dict], self._request("GET", "/api/repos/list"))

    @staticmethod
    def _build_repo_payload(
        url: str, distro: str, package_override: str | None = None
    ) -> dict[str, str | None]:
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        parsed_url = urlparse(url)
        path_parts = parsed_url.path.strip("/").split("/")

        if len(path_parts) != 2 or not parsed_url.netloc:
            raise ValueError(
                "Invalid repository URL. Expected format: https://<host>/<owner>/<repo>"
            )

        return {
            "host": parsed_url.netloc,
            "owner": path_parts[0],
            "repo_name": path_parts[1],
            "package_name": package_override if package_override else None,
            "distro": distro,
        }

    @staticmethod
    def _api_error(error: requests.exceptions.HTTPError) -> APIError:
        if error.response is not None:
            if "application/json" in error.response.headers.get("Content-Type", ""):
                error_json = cast(dict[str, object], error.response.json())
                error_data = str(error_json.get("detail", str(error)))
            else:
                error_data = str(error)

            status_code: int | str = error.response.status_code

        else:
            error_data = str(error)
            status_code = "Unknown"

        return APIError(f"HTTP {status_code}: {error_data}")
