class RepoClientError(Exception):
    """Base exception for client-side logic erorrs."""


class RepoNotFoundError(RepoClientError):
    """Raised when no repositories match the query."""

    def __init__(self, name: str):
        super().__init__(f"No tracked repo matching '{name}'")
        self.name = name


class AmbiguousRepoError(RepoClientError):
    """Raised when a query matches multiple repositories."""

    def __init__(self, name: str, matches: list[dict]):
        super().__init__(f"'{name}' matches multiple tracked repos.")
        self.name = name
        self.matches = matches
