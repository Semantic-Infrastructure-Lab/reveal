"""The one place reveal gets a tree-sitter parser or tree (BACK-1045).

Every caller used to import ``tree_sitter_language_pack.get_parser`` and call it
itself: 25 sites, 16 of them in adapters. Only the file analyzer
(``reveal/treesitter.py``) warned when a grammar was missing, so an adapter whose
grammar was missing returned the same empty result as a file with nothing in it.
Here, acquiring a parser either succeeds or raises ``GrammarUnavailable``, and the
warning before a first-use network fetch (BACK-979) is given once per language,
whichever caller hits it first.

The pack's functions are looked up on the module at call time, not imported by name,
so a test that patches ``tree_sitter_language_pack.get_parser`` reaches every caller.
``scripts/check_boundaries.py`` (rule ``tree-sitter-import``) keeps the pack's imports
in ``reveal/core/treesitter*.py``.
"""

import logging
from typing import Any, Iterable, Set

from .treesitter_compat import ts_parse

logger = logging.getLogger(__name__)

# Languages already warned about (not downloaded yet), and languages a parser was
# obtained for -- their grammar is in the local cache, so they need no check.
_warned_uncached: Set[str] = set()
_ready: Set[str] = set()


class GrammarUnavailable(RuntimeError):
    """No parser for *language*: the pack isn't installed, doesn't know the
    language, or couldn't fetch its grammar. The caller decides what that means for
    its result; it must not read as "nothing found"."""

    def __init__(self, language: str, cause: BaseException):
        super().__init__(f"no tree-sitter grammar for {language!r}: {cause}")
        self.language = language
        self.cause = cause


def _pack(language: str) -> Any:
    try:
        import tree_sitter_language_pack
    except ImportError as e:
        raise GrammarUnavailable(language, e) from e
    return tree_sitter_language_pack


def downloaded_languages() -> Set[str]:
    """Grammars in the local cache: a directory read, never a network fetch.
    Empty when the language pack isn't installed."""
    try:
        return set(_pack('*').downloaded_languages())
    except GrammarUnavailable:
        return set()


def get_parser(language: str, *, announce_fetch: bool = True) -> Any:
    """A parser for *language*, or ``GrammarUnavailable``.

    ``tree_sitter_language_pack.get_parser`` downloads a grammar on its first use.
    With *announce_fetch*, say so once per language before that fetch, so an offline
    host learns why the parse is slow or fails (BACK-979)."""
    pack = _pack(language)
    if announce_fetch and language not in _ready and language not in _warned_uncached:
        if language not in downloaded_languages():
            _warned_uncached.add(language)
            logger.warning(
                "tree-sitter grammar for %r not yet downloaded — first parse "
                "will attempt to fetch it from the network (see "
                "INSTALL.md#network-requirements for offline setups)",
                language,
            )
    try:
        parser = pack.get_parser(language)
    except Exception as e:  # noqa: BLE001 - the pack raises its own types (LookupError, download errors)
        raise GrammarUnavailable(language, e) from e
    _ready.add(language)
    return parser


def get_tree(language: str, source: str) -> Any:
    """Parse *source* as *language*. Raises ``GrammarUnavailable`` when there is no
    parser; a tree with ERROR nodes is still a tree (see ``tree_has_recovery_artifacts``)."""
    return ts_parse(get_parser(language), source)


def has_grammar(language: str) -> bool:
    """Whether a parser for *language* can be had, without announcing a fetch."""
    try:
        get_parser(language, announce_fetch=False)
    except GrammarUnavailable:
        return False
    return True


def download(languages: Iterable[str]) -> int:
    """Fetch the named grammars into the local cache; returns how many."""
    return int(_pack('*').download(list(languages)))


def download_all() -> int:
    """Fetch every grammar the pack knows into the local cache; returns how many."""
    return int(_pack('*').download_all())
