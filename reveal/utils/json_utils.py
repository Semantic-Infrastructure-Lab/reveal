"""JSON utilities for reveal."""

import json
import sys
from datetime import datetime, date


class DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime and date objects."""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


def safe_json_dumps(obj, **kwargs):
    """Safely dump JSON with support for datetime/date objects."""
    kwargs.setdefault('cls', DateTimeEncoder)
    kwargs.setdefault('indent', 2)
    return json.dumps(obj, **kwargs)


def print_json_result(result, file=None) -> None:
    """Print a reveal result dict as JSON — the single funnel for adapter/
    renderer CLI JSON output (BACK-893). Not for printing arbitrary values
    extracted *from* a result (e.g. a queried JSON file's own content) —
    those should keep using plain json.dumps/safe_json_dumps directly.
    """
    print(safe_json_dumps(result), file=file or sys.stdout)
