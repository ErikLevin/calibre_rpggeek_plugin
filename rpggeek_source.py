"""The module containing the plugin class."""

import re
from datetime import datetime
from functools import total_ordering
from queue import Queue
from urllib.parse import ParseResult, urlparse

from bs4 import BeautifulSoup
from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Source

_ID_TYPE = "rpggeek"
_API_THING_URL = "https://rpggeek.com/xmlapi2/thing?id="
_API_SEARCH_URL = "https://rpggeek.com/xmlapi2/search?type=rpgitem&query="

# TODO Was this URL correct? Check again...
# _WEB_SEARCH_URL = (
#     "https://rpggeek.com/geeksearch.php?action=search&objecttype=rpgitem&"
#     'searchinfilters=[{"filtertype":"geekitemtype","filtertext":"RPG Item"}'
#     ',{"filtertype":"itemtype","filtertext":"RPG Item"}]&B1=Search&q='
# )


def _get_pub_date(soup: BeautifulSoup) -> datetime | None:
    tag = soup.find("yearpublished")
    if not tag:
        return None
    year = int(tag["value"])
    if year <= 0:
        return None
    return datetime(year, 1, 1)


def _get_publisher(soup: BeautifulSoup) -> str | None:
    # There can be many publishers. Just using first one for now. Need to scrape
    # for versions to narrow down actual publisher.
    tag = soup.find("link", attrs={"type": "rpgpublisher"})
    if tag:
        return tag["value"]
    return None


def _get_series(soup: BeautifulSoup) -> tuple[str, int]:
    series = ""
    index = 0
    # Same here, take first series for now...
    series_tag = soup.find("link", attrs={"type": "rpgseries"})
    if series_tag:
        series = series_tag["value"]
    # Guess that the last number in seriescode is the series index
    # Any way to do better? Probably not?
    series_code_tag = soup.find("seriescode")
    if series_code_tag:
        series_code = series_code_tag["value"]
        match = re.search(r"(\d+)\D*$", series_code)
        index = int(match.group(1)) if match else 0
    return series, index


def _get_comments(soup: BeautifulSoup) -> str | None:
    tag = soup.find("description")
    if not tag or not tag.contents:
        return None
    return tag.contents[0]


class RPGGeekSource(Source):
    """The plugin class."""

    name = "RPGGeek"
    description = "Retrieves metadata from RPGGeek"
    version = (0, 0, 1)
    author = "Erik Levin"
    supported_platforms = ["windows", "osx", "linux"]
    capabilities = frozenset(["identify"])
    touched_fields = frozenset(
        [
            "identifier:rpggeek",
            "title",
            "authors",
            "comments",
            "pubdate",
            "publisher",
            "series",
        ]
    )

    # TODO Future work - settings
    # - What to use as authors. First designer, all designers, fallback to artists,
    #   fallback to producers, fallback to publishers.
    # - Setting various things as designated tags. rpg, rpgsetting, rpggenre
    # - Use original published date or specific version published date
    def is_customizable(self):
        """Return whether this plugin has config."""
        return False

    # TODO Future work - cover art
    # - get_cached_cover_url
    # - download_cover

    # TODO Future work - ISBN, product code, and language. Need to get them from
    # rpgitemversion, which aren't in the API, so, need to search and scrape.

    # TODO When I have rpgitemversion, get actual publisher from there instead.

    def get_book_url(self, identifiers):
        """Return ("rpggeek", RPGGeek item ID, RPG item URL), based on RPGGeek item ID.

        Returns None if there is no RPGGeek ID.
        See parent class for more information.
        """
        rpggeek_id = identifiers.get(_ID_TYPE, None)
        if rpggeek_id:
            return (
                _ID_TYPE,
                rpggeek_id,
                "https://rpggeek.com/rpgitemversion/" + rpggeek_id,
            )
        return None

    def id_from_url(self, url) -> tuple[str, str] | None:
        """Return ("rpggeek", RPG item ID) from RPG item URL, or None if that fails.

        See parent class for more information.
        """
        parsed_url: ParseResult = urlparse(url)
        # xGeek's three domains are interchangeable
        if parsed_url.netloc not in (
            "rpggeek.com",
            "boardgamegeek.com",
            "videogamegeek.com",
        ):
            return None

        path_parts: list[str] = parsed_url.path.strip("/").split("/")
        if len(path_parts) < 2 or path_parts[0] != "rpgitemversion":
            return None
        return (_ID_TYPE, path_parts[1])

    def identify_results_keygen(self, title=None, authors=None, identifiers=None):
        """Sort results based on RPGGeek's search result sorting instead."""
        if not identifiers:
            identifiers = {}
        if not authors:
            authors = []

        @total_ordering
        class _KeyGen:
            def __init__(self, metadata):
                self.relevance = metadata.source_relevance

            def __eq__(self, other):
                return self.relevance == other.relevance

            def __ne__(self, other):
                return self.relevance != other.relevance

            def __lt__(self, other):
                return self.relevance < other.relevance

            def __le__(self, other):
                return self.relevance <= other.relevance

            def __gt__(self, other):
                return self.relevance > other.relevance

            def __ge__(self, other):
                return self.relevance >= other.relevance

        def keygen(metadata):
            return _KeyGen(metadata)

        return keygen

    def _get_metadata_from_thing_api(
        self, rpggeek_id: str, result_queue: Queue, relevance: int, log
    ) -> None:
        response = self.browser.open_novisit(_API_THING_URL + rpggeek_id)
        soup = BeautifulSoup(response, features="lxml")
        log.debug(soup.prettify())
        if not soup.find("item", attrs={"type": "rpgitem"}):
            return
        title = soup.find("name", attrs={"type": "primary"})["value"]
        authors = [
            x["value"] for x in soup.find_all("link", attrs={"type": "rpgdesigner"})
        ]
        pub_date = _get_pub_date(soup)
        publisher = _get_publisher(soup)
        series, index = _get_series(soup)
        comments = _get_comments(soup)

        metadata = Metadata(title, authors)
        metadata.set_identifier(_ID_TYPE, rpggeek_id)
        metadata.pubdate = pub_date
        metadata.publisher = publisher
        metadata.series = series
        metadata.comments = comments
        metadata.series_index = index
        metadata.source = self.name
        metadata.source_relevance = relevance
        self.clean_downloaded_metadata(metadata)
        result_queue.put(metadata)

    def _search_title(self, title: str, result_queue: Queue, log) -> None:
        """Search for item based on title, using API."""
        title_tokens = self.get_title_tokens(title)
        query = "+".join(title_tokens)
        query = _API_SEARCH_URL + query
        log.debug(query)
        response = self.browser.open_novisit(query)

        soup = BeautifulSoup(response, features="lxml")
        log.debug(soup.prettify())

        items = soup.find_all("item", attrs={"type": "rpgitem"})
        # TODO You can get multiple things from one query
        # Query for all search results with one API call instead of the below.
        for i, item in enumerate(items):
            self._get_metadata_from_thing_api(
                item["id"], result_queue, relevance=i, log=log
            )

    def identify(
        self,
        log,
        result_queue,
        abort,
        title=None,
        authors=None,
        identifiers=None,
        timeout=30,
    ):  # pylint: disable=too-many-arguments
        """See parent class."""
        if not identifiers:
            identifiers = {}
        if not authors:
            authors = []

        # TODO Respect abort and timeout...

        rpggeek_id = identifiers.get(_ID_TYPE, None)
        if rpggeek_id:
            self._get_metadata_from_thing_api(
                rpggeek_id, result_queue, relevance=0, log=log
            )
        else:
            self._search_title(title, result_queue, log)
