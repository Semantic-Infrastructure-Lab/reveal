"""The one time-window codec (COMMAND_MODEL "Time window", Scott 2026-11-22, BACK-2728).

``--since``/``--until`` take one grammar on every noun that reads them: ``today``, a period (``YYYY``, ``YYYY-MM``,
``YYYY-MM-DD``) or a time (``YYYY-MM-DD[T ]HH:MM[:SS[.f]]``, an optional ``Z`` or ``+HH:MM``/``-HH:MM``), on the
calendar. Each noun declares its bound with ``time_window_param``, so a malformed one is an invalid request (exit 2
naming the control and the forms) before analysis, on every transport. The codec returns the text unchanged: each noun
keeps its own comparison (Claude and Codex compare text with the whole ``until`` day, Git at the bound's precision,
Metrics from the bound's start, ``bound_start``), and ``resolve_today`` gives ``today`` one meaning, the local date.
The rule lives on the declaration, never in the binder keyed on the word: Pack's ``since`` is a git ref.

The grammar is the one Git's ``date`` where terms are compared in (BACK-2277, BACK-2300, BACK-2309).
"""
import re
from datetime import date
from typing import Any, Callable, Optional, Tuple, overload

from .query_parser import CliBinding, ParamSpec, ParamValueError, one_value

# A bound written as a year, a month or a day, no time: `date>2026`, `date>2026-02`,
# `date>2026-02-01`.
PERIOD = re.compile(r'\d{4}(-\d{2}(-\d{2})?)?')
# A timestamp written with 'T' between the day and the time: `2026-02-01T12:00:00`.
T_SEPARATED = re.compile(r'(\d{4}-\d{2}-\d{2})T(\d)')
# A timestamp with a zone: `2026-02-01T12:00:00Z`, `2026-02-01 12:00+02:00`, `...12:00:00-1200`.
ZONED = re.compile(r'(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?) ?(Z|[+-]\d{2}:?\d{2})',
                   re.IGNORECASE)
# Any time of a day, zoned or not, its fields captured for the calendar check.
_TIME = re.compile(r'(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?: ?(?:Z|[+-](\d{2}):?(\d{2})))?',
                   re.IGNORECASE)
TODAY = 'today'
FORMS = ('today, a period (YYYY, YYYY-MM or YYYY-MM-DD) or a time (YYYY-MM-DD[T ]HH:MM[:SS[.f]], optional Z, +HH:MM '
         'or -HH:MM)')


def _is_day(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:  # month 13, February 30, year 0
        return False
    return True


def is_time_bound(value: Any) -> bool:
    """Whether *value* is written in the grammar and names a real day and time (``2026-02-30`` does not)."""
    if not isinstance(value, str):
        return False
    if value == TODAY:
        return True
    if PERIOD.fullmatch(value):
        year, month, day = (int(part) for part in (value.split('-') + ['1', '1'])[:3])
        return _is_day(year, month, day)
    time = _TIME.fullmatch(value)
    if time is None:
        return False
    year, month, day, hour, minute, second, zone_hours, zone_minutes = (int(part or 0) for part in time.groups())
    return _is_day(year, month, day) and hour < 24 and minute < 60 and second < 60 and zone_hours < 24 \
        and zone_minutes < 60


def time_bound(name: str) -> Callable[[Any], str]:
    """The converter of the time bound *name*: the text unchanged, or an invalid request naming *name* and the forms. A
    typed list of equal bounds is that bound, two different ones are an invalid request naming both (a setting)."""
    def convert(value: Any) -> str:
        text = one_value(value) if isinstance(value, (list, tuple)) else value
        if not is_time_bound(text):
            raise ParamValueError(f'{name} must be {FORMS}, got {text!r}')
        return text
    return convert


@overload
def resolve_today(value: str) -> str: ...
@overload
def resolve_today(value: None) -> None: ...
def resolve_today(value: Optional[str]) -> Optional[str]:
    """``today`` as the local date (``YYYY-MM-DD``), the one meaning on every noun; any other bound unchanged."""
    return date.today().isoformat() if value == TODAY else value


def bound_start(value: str) -> str:
    """The first instant of a valid bound, as text ``datetime.fromisoformat`` reads: a period's first day, today's
    date, a time as written (a lowercase zone ``z`` upper-cased). Metrics' churn walk starts there."""
    value = resolve_today(value)
    if PERIOD.fullmatch(value):
        return value + '-01' * ((10 - len(value)) // 3)
    return value[:-1] + 'Z' if value.endswith('z') else value


def time_window_param(name: str, description: str, *, answers: Tuple[str, ...] = (), requires: Tuple[str, ...] = (),
                      examples: Tuple[str, ...] = (), role: Optional[str] = None,
                      metavar: Optional[str] = None) -> ParamSpec:
    """The one declaration of a noun's time bound (``since``/``until``): a scalar setting with its flag, read with the
    shared codec. *description* says what the bound limits; the forms are appended."""
    return ParamSpec(name, 'string', f'{description}. Takes {FORMS}', None, time_bound(name), examples, role=role,
                     cli=CliBinding((f'--{name}',), metavar=metavar), answers=answers, requires=requires)
