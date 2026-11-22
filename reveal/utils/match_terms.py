"""Match terms of the session nouns, Claude and Codex (COMMAND_MODEL "Conflicting values", rule 19, BACK-2654): a
repeated match ANDs its terms per row of the answer, and every answer echoes its terms through one seam.

An empty term is an invalid request on every noun (COMMAND_MODEL "Empty match term", Scott 2026-11-22, BACK-2736):
the binder refuses one in any spelling of a term control (``query_binding``), with the one message built here."""
from dataclasses import dataclass
from typing import Any, List, Sequence, Union

from ..errors import RequestValidationError
from .query_parser import ParamValueError

# The shared controls whose values are terms, with the term a refusal teaches: a match's text, a where's expressions.
TERM_EXAMPLES = {'match': '--match TEXT', 'where': '--where FIELD OP VALUE'}


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


def is_blank_term(value: Any) -> bool:
    """Whether *value* states an empty term: an empty or whitespace-only string, or a list (a repeated term) holding
    one. Whitespace is no term, as xlsx ruled first (BACK-2525): it matched every row holding a space elsewhere."""
    items = value if isinstance(value, (list, tuple)) else [value]
    return any(isinstance(item, str) and not item.strip() for item in items)


def empty_term_message(spelling: str, example: str) -> str:
    """The one refusal of an empty term: the spelling as the request typed it, and the term it needs."""
    return f'{spelling} needs a term: {example}'


def empty_term_error(spelling: str, example: str) -> RequestValidationError:
    """An empty term, an invalid request (exit 2) on every transport."""
    return RequestValidationError(empty_term_message(spelling, example))


@dataclass(frozen=True)
class TermValue:
    """The converter of a text-valued word that states a term without being a match or a where: a standalone word or a
    legacy filter a term replaces (Claude ``?search``, ``?contains``, ``--name``; Codex ``?search``). Declared, it tells
    the binder the control is a term, so an empty one is refused in any spelling, named as typed; called directly (a
    library ``ParamSpec.validate``), it refuses one naming *spelling*. Otherwise a string without NUL, as given."""
    spelling: str
    example: str

    def __call__(self, value: Any) -> str:
        if not isinstance(value, str) or '\x00' in value:
            raise ValueError('expected a string without NUL')
        if is_blank_term(value):
            raise ParamValueError(empty_term_message(self.spelling, self.example))
        return value
