"""Tests the RPGGeek metadata source plugin."""

from queue import Queue
from typing import Callable, Any
from calibre.ebooks.metadata.sources.test import (
    test_identify_plugin,
    title_test,
    authors_test,
    pubdate_test,
    series_test,
    # isbn_test,
)
from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import create_log

# No variant of import (absolute/relative) makes this work both for pylint and when
# running through calibre-debug. So just suppress import warning.
from rpggeek_source import RPGGeekSource  # pylint: disable=import-error

# TODO It would make a lot more sense if the tests would rely on a test double that
# returns saved data, instead of relying on RPGGeek's actual, live API and a working
# internet connection. Searches, especially, can change results at any time...
# But since Calibre's test framework seems to rely on actually installing the plugin
# and running it, this seems nontrivial.


# region "unit tests"


# For some reason, I can't get it to work to run unittest via calibre-debug.
# It refuses to discover any tests. So, making a few assertion functions of my own.


def assert_eq(first: Any, second: Any) -> None:
    """Fail if the two parameters are not equal."""
    if first != second:
        raise AssertionError(f"{first} was not equal to {second}!")


def assert_true(expr: bool):
    """Fail if parameter is not True."""
    if not expr:
        raise AssertionError("Expression was False!")


def _test_get_book_url():
    _test_get_book_url__normal_case()
    _test_get_book_url__no_id()


def _test_get_book_url__normal_case():
    assert_eq(
        (
            "rpggeek",
            "303391",
            "https://rpggeek.com/rpgitem/303391",
        ),
        rpggeek_source.get_book_url({"rpggeek": "303391"}),
    )


def _test_get_book_url__no_id():
    assert_eq(None, rpggeek_source.get_book_url({"isbn": "123456789"}))


def _test_id_from_url():
    _test_id_from_url__normal_url()
    _test_id_from_url__no_title()
    _test_id_from_url__alt_domain()
    _test_id_from_url__invalid_url()


def _test_id_from_url__normal_url():
    assert_eq(
        ("rpggeek", "303391"),
        rpggeek_source.id_from_url(
            "https://rpggeek.com/rpgitem/303391/gamemastery-guide"
        ),
    )


def _test_id_from_url__no_title():
    assert_eq(
        ("rpggeek", "303391"),
        rpggeek_source.id_from_url("https://rpggeek.com/rpgitem/303391"),
    )


def _test_id_from_url__alt_domain():
    assert_eq(
        ("rpggeek", "303391"),
        rpggeek_source.id_from_url("https://boardgamegeek.com/rpgitem/303391"),
    )


def _test_id_from_url__invalid_url():
    assert_eq(
        None,
        rpggeek_source.id_from_url(
            "https://example.com/rpgitem/303391/gamemastery-guide"
        ),
    )
    assert_eq(
        None,
        rpggeek_source.id_from_url(
            "https://rpggeek.com/rpg/56388/pathfinder-roleplaying-game-2nd-edition"
        ),
    )


def _test_id_with_no_match():
    result_queue = Queue()
    rpggeek_source.identify(
        result_queue=result_queue,
        identifiers={"rpggeek": "0"},
        log=create_log(),
        abort=False,
    )
    assert_true(result_queue.empty())


def _test_id_is_not_rpgitem():
    result_queue = Queue()
    rpggeek_source.identify(
        result_queue=result_queue,
        identifiers={"rpggeek": "13"},  # this 'thing' in the API is a board game
        log=create_log(),
        abort=False,
    )
    assert_true(result_queue.empty())


def _test_no_search_hits():
    result_queue = Queue()
    rpggeek_source.identify(
        # I asked ChatGPT for "the name of an RPG book that absolutely does
        # not exist". It delivered.
        title="The Tome of Unending Misfortunes: A Guide to Living a Life of Constant "
        "Suffering in Your RPG Adventures",
        result_queue=result_queue,
        log=create_log(),
        abort=False,
    )
    assert_true(result_queue.empty())


# endregion


def identifier_test(id_type: str, id_val: str) -> Callable[[Metadata], bool]:
    """Return function that tests if metadata contains specific identifier."""

    def test(metadata: Metadata) -> bool:
        metadata_id = metadata.get_identifiers()[id_type]
        if metadata_id and metadata_id == id_val:
            return True
        print(f"Identifier test failed. Expected: {id_val}' found {metadata_id}")
        return False

    return test


def publisher_test(publisher: str) -> Callable[[Metadata], bool]:
    """Return function that tests if metadata has correct publisher set."""

    def test(metadata: Metadata) -> bool:
        if metadata.publisher and metadata.publisher == publisher:
            return True
        print(
            f"Publisher test failed. Expected: {publisher}' found {metadata.publisher}"
        )
        return False

    return test


def pubdate_none_test() -> Callable[[Metadata], bool]:
    """Return function that tests if metadata has None pubdate."""

    def test(metadata: Metadata) -> bool:
        return metadata.pubdate is None

    return test


if __name__ == "__main__":
    # To run these test use:
    # calibre-debug -e test.py

    rpggeek_source = RPGGeekSource(None)
    _test_get_book_url()
    _test_id_from_url()
    _test_id_with_no_match()
    _test_id_is_not_rpgitem()
    _test_no_search_hits()

    test_identify_plugin(
        RPGGeekSource.name,
        [
            (  # RPGGeek ID -> item with title, authors, pubdate, publisher, identifier
                {
                    "identifiers": {"rpggeek": "363105"},
                },
                [
                    title_test("A Fistful of Flowers", exact=True),
                    authors_test(["Eleanor Ferron", "Linda Zayas-Palmer"]),
                    pubdate_test(2022, 1, 1),
                    publisher_test("Devir"),
                    identifier_test("rpggeek", "363105"),
                ],
            ),
            (  # RPGGeek ID -> item with non-ASCII title
                {
                    "identifiers": {"rpggeek": "293597"},
                },
                [
                    title_test("永い後日談のネクロニカ", exact=True),
                ],
            ),
            (  # RPGGeek ID -> item with uncredited designer
                {
                    "identifiers": {"rpggeek": "329480"},
                },
                [
                    title_test("Abomination Vaults Pawn Collection"),
                    authors_test(["(Uncredited)"]),
                ],
            ),
            (  # RPGGeek ID -> item without published year
                {
                    "identifiers": {"rpggeek": "61154"},
                },
                [
                    title_test("Creatures of the Nightcycle"),
                    pubdate_none_test(),
                ],
            ),
            (  # RGPGeek ID -> item with series and index
                {
                    "identifiers": {"rpggeek": "346266"},
                },
                [
                    title_test("Spoken on the Song Wind", exact=True),
                    series_test("Pathfinder Adventure Path", 170),
                ],
            ),
            (  # Title -> one matching search result
                {"title": "A Fistful of Flowers"},
                [
                    title_test("A Fistful of Flowers", exact=True),
                    authors_test(["Eleanor Ferron", "Linda Zayas-Palmer"]),
                    pubdate_test(2022, 1, 1),
                    publisher_test("Devir"),
                    identifier_test("rpggeek", "363105"),
                ],
            ),
            (  # Title -> many search results
                {"title": "GameMastery Guide"},
                [
                    # Check that a non-first result is returned
                    title_test("GameMastery Guide", exact=True),
                    identifier_test("rpggeek", "303391"),
                ],
            ),
        ],
        fail_missing_meta=False,
    )

    print("SUCCESS!")
