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


_provenance_enabled = False


def set_provenance_enabled(enabled: bool) -> None:
    """Toggle whether print_json_result attaches an 'execution' provenance
    block (BACK-881). Set once from CLI arg parsing (--provenance); read by
    every print_json_result call thereafter. A module-level toggle — not a
    parameter threaded through every renderer signature — because most
    renderer call sites only receive the result dict and a format string,
    not the parsed argparse.Namespace.
    """
    global _provenance_enabled
    _provenance_enabled = enabled


def print_json_result(result, file=None) -> None:
    """Print a reveal result dict as JSON — the single funnel for adapter/
    renderer CLI JSON output (BACK-893). Not for printing arbitrary values
    extracted *from* a result (e.g. a queried JSON file's own content) —
    those should keep using plain json.dumps/safe_json_dumps directly.

    When provenance is enabled (see set_provenance_enabled), attaches an
    'execution' block to dict results that don't already carry one.
    """
    if _provenance_enabled and isinstance(result, dict) and 'execution' not in result:
        from .provenance import build_execution_provenance
        result = {**result, 'execution': build_execution_provenance()}
    print(safe_json_dumps(result), file=file or sys.stdout)
