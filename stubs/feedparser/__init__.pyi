"""Focused type information for the feedparser API used by this project.

feedparser 6.0.14 does not ship a ``py.typed`` marker or inline type hints.
"""

from typing import Literal, overload


class FeedParserDict:
    """The mapping-like value returned for a parsed feed or an entry."""

    entries: list[FeedParserDict]

    @overload
    def __getitem__(self, key: Literal["link", "title"], /) -> str: ...

    @overload
    def __getitem__(self, key: str, /) -> object: ...


def parse(
    url_file_stream_or_string: str | bytes,
    /,
    *args: object,
    **kwargs: object,
) -> FeedParserDict: ...
