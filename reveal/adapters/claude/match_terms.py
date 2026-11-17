"""Claude's match terms (COMMAND_MODEL "Conflicting values", rule 19, BACK-2654): a repeated match ANDs its terms per
row of the answer, and every answer echoes its terms through one seam."""
from typing import Any, List, Sequence, Union


def match_terms(value: Any) -> List[str]:
    """The distinct terms of a match value, in order: a string, or the list a repeated match binds to."""
    items = [value] if isinstance(value, str) else list(value or ())
    return list(dict.fromkeys(items))


def holds_all(text: str, terms: Sequence[str]) -> bool:
    """Whether *text* holds every term (case-insensitive substrings)."""
    lowered = text.lower()
    return all(term.lower() in lowered for term in terms)


def term_echo(terms: Sequence[str]) -> List[str]:
    """How an answer echoes its match terms: the one seam for the JSON shape. Always the list of terms, one term
    included, so each echo field has one type (Scott 2026-11-16, BACK-2654 note #13)."""
    return list(terms)


def term_label(echo: Union[str, Sequence[str], None]) -> str:
    """The echoed terms as text renderers print them: one term as itself, several joined by AND."""
    if echo is None or isinstance(echo, str):
        return echo or ''
    return ' AND '.join(echo)
