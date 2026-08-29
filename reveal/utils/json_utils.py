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


def attach_provenance(result):
    """Return *result* with an 'execution' provenance block attached, if
    provenance is enabled (see set_provenance_enabled) and it doesn't
    already carry one. No-op otherwise. BACK-1034: `cli/commands/{overview,
    check,pack}.py` build their own Output Contract envelope and call
    json.dumps directly rather than going through print_json_result — call
    this before that json.dumps so --provenance isn't silently dropped on
    those CLI subcommands.
    """
    if _provenance_enabled and isinstance(result, dict) and 'execution' not in result:
        from .provenance import build_execution_provenance
        return {**result, 'execution': build_execution_provenance()}
    return result


def write_also_json(result, args) -> None:
    """BACK-1184: write *result* as JSON to args.also_json, if set, alongside
    whatever --format is already rendering to stdout. Lets one invocation
    produce both a human-readable report and a machine-readable artifact
    without a second reveal call re-parsing the same files. No-op when
    --also-json wasn't passed, or when --format is already json (the primary
    output already covers it).
    """
    path = getattr(args, 'also_json', None)
    if not path or getattr(args, 'format', 'text') == 'json':
        return
    with open(path, 'w') as f:
        print_json_result(result, file=f)


def print_json_result(result, file=None) -> None:
    """Print a reveal result dict as JSON — the single funnel for adapter/
    renderer CLI JSON output (BACK-893). Not for printing arbitrary values
    extracted *from* a result (e.g. a queried JSON file's own content) —
    those should keep using plain json.dumps/safe_json_dumps directly.

    When provenance is enabled (see set_provenance_enabled), attaches an
    'execution' block to dict results that don't already carry one.
    """
    print(safe_json_dumps(attach_provenance(result)), file=file or sys.stdout)
