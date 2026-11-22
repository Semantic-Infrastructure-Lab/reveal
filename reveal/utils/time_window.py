"""The time-window grammar: the bounds ``--since``/``--until`` and Git's ``date`` where terms are written in.

Git's comparison owned it first (BACK-2277, BACK-2300, BACK-2309); the shared time-window codec reads the same forms
(COMMAND_MODEL "Time window", BACK-2728).
"""
import re

# A bound written as a year, a month or a day, no time: `date>2026`, `date>2026-02`,
# `date>2026-02-01`.
PERIOD = re.compile(r'\d{4}(-\d{2}(-\d{2})?)?')
# A timestamp written with 'T' between the day and the time: `2026-02-01T12:00:00`.
T_SEPARATED = re.compile(r'(\d{4}-\d{2}-\d{2})T(\d)')
# A timestamp with a zone: `2026-02-01T12:00:00Z`, `2026-02-01 12:00+02:00`, `...12:00:00-1200`.
ZONED = re.compile(r'(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?) ?(Z|[+-]\d{2}:?\d{2})',
                   re.IGNORECASE)
