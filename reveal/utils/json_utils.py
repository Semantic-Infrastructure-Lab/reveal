"""JSON utilities for reveal."""

import contextlib
import io
import json
import os
import sys
from datetime import datetime, date

from .query_parser import attach_input_warnings


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


def attach_retirements(result):
    """Return *result* with a ``retired_spelling`` entry in ``meta.warnings`` for each retired
    spelling this invocation used (the stderr note's fact for a reader of the JSON; ground
    rule 7). The result itself is not mutated; one with nothing to add is returned as is."""
    if not isinstance(result, dict):
        return result
    from ..cli.invocation import retirement_warnings
    entries = retirement_warnings()
    if not entries:
        return result
    meta = dict(result['meta']) if isinstance(result.get('meta'), dict) else {}
    warnings = list(meta['warnings']) if isinstance(meta.get('warnings'), list) else []
    seen = {w.get('field') for w in warnings if isinstance(w, dict) and w.get('code') == 'retired_spelling'}
    meta['warnings'] = warnings + [entry for entry in entries if entry['field'] not in seen]
    return {**result, 'meta': meta}


def file_sinks(args) -> list:
    """(format, path) of every file sink the invocation requested, in the order given.

    ``--output FORMAT=PATH`` specs (a bare FORMAT is the stdout sink and was consumed by
    ``apply_output_sinks``), then the retired ``--also-json PATH`` as a json sink. The one reader of
    both spellings, so a writer asks for sinks and never for a flag (BACK-2089). ``isinstance`` rather
    than truthiness: ``args`` is a Mock in several callers' tests.
    """
    sinks: list = []
    specs = getattr(args, 'output', None)
    if isinstance(specs, list):
        sinks.extend((spec.partition('=')[0], spec.partition('=')[2])
                     for spec in specs if isinstance(spec, str) and '=' in spec)
    legacy = getattr(args, 'also_json', None)
    if isinstance(legacy, (str, os.PathLike)) and legacy:
        sinks.append(('json', legacy))
    return sinks


def json_sink_paths(args) -> list:
    """The paths of the json file sinks: what a writer that only knows the JSON document asks for."""
    return [path for fmt, path in file_sinks(args) if fmt == 'json']


def _render_sink(result, fmt, render, render_kwargs) -> str:
    """The text *render* prints for *result* in *fmt*, as the stdout sink would print it: the body, the
    result's warnings, then each cut list once. What it prints to stderr was already said by the stdout
    sink, so it is dropped."""
    from ..display.formatting import print_result_control_notes
    from ..rendering.base import emit_rendered
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
        emit_rendered(render, result, fmt, **render_kwargs)
        print_result_control_notes(result, fmt)
    return buffer.getvalue()


def write_also_json(result, args, render=None, **render_kwargs) -> None:
    """Write *result* to every file sink the invocation asked for (BACK-1184, BACK-2089): one result, one
    write per sink, each sink rendered on its own.

    A ``json`` sink is the result as JSON; any other format is what *render* prints for it
    (``render(result, fmt, **render_kwargs)``, the call the stdout sink makes). A json sink is a no-op
    when the stdout sink is already json: the primary output covers it. Every sink is attempted; the first
    failure is raised after the rest were tried, tagged with its format (``sink_format``) for the one
    disclosure line in ``write_requested_artifact``, and any later failure is disclosed there as well.
    A non-json sink on a path that cannot render it fails like an unwritable one.
    """
    failures: list = []
    primary = getattr(args, 'format', 'text')
    for fmt, path in file_sinks(args):
        if fmt == 'json' and primary == 'json':
            continue
        try:
            if fmt == 'json':
                with open(path, 'w', encoding='utf-8') as f:
                    print_json_result(result, file=f)
            elif render is None:
                raise ValueError(f'{path}: this output cannot be rendered as {fmt}')
            else:
                write_text_artifact(path, _render_sink(result, fmt, render, render_kwargs))
        except ARTIFACT_WRITE_ERRORS as exc:
            setattr(exc, "sink_format", fmt)  # read back by _disclose_failed_sink
            failures.append(exc)
    if failures:
        for later in failures[1:]:
            _disclose_failed_sink(later)
        raise failures[0]


# What a requested artifact write raises: no path (OSError), an unencodable value, a bad serialization.
ARTIFACT_WRITE_ERRORS = (OSError, UnicodeError, ValueError)


def write_text_artifact(path, text) -> None:
    """Write an already-rendered artifact document to *path* (raises ARTIFACT_WRITE_ERRORS).

    *path* may be several paths: each is written, and the first failure is raised once the rest were tried.
    """
    paths = [path] if isinstance(path, (str, os.PathLike)) else list(path)
    first = None
    for one in paths:
        try:
            with open(one, 'w', encoding='utf-8') as f:
                f.write(text)
        except ARTIFACT_WRITE_ERRORS as exc:
            first = first or exc
    if first is not None:
        raise first


def _disclose_failed_sink(exc) -> str:
    """Say once, on stderr, that a requested sink failed; returns the line's text (the json sink keeps the
    wording that named it a JSON artifact)."""
    fmt = getattr(exc, 'sink_format', 'json')
    kind = 'JSON artifact' if fmt == 'json' else f'{fmt} output sink'
    message = f'Requested {kind} failed: {exc}'
    print(f'Error: {message}', file=sys.stderr)  # boundary-ok: print -- the one disclosure line for a failed requested artifact, shared by declared nouns and check
    return message


def write_requested_artifact(write, result=None):
    """Run *write*, the writer of a file the caller asked for beside its primary answer.

    The one owner of what a failed requested artifact means (D6, "requested output failed"):
    it is disclosed once on stderr and recorded in ``result['meta']['output_errors']`` when a
    result dict is given. Returns the exception so the caller maps it to exit 3 (declared
    nouns through ``emit_declared_result``, native check through ``check_exit_code``); None
    when the write succeeded. Flag-agnostic: ``--also-json`` is one spelling that reaches it.
    """
    try:
        write()
    except ARTIFACT_WRITE_ERRORS as exc:
        message = _disclose_failed_sink(exc)
        if isinstance(result, dict):
            result.setdefault('meta', {}).setdefault('output_errors', []).append(
                {'code': 'artifact_write_failed', 'message': message})
        return exc
    return None


def print_json_result(result, file=None) -> None:
    """Print a reveal result dict as JSON — the single funnel for adapter/
    renderer CLI JSON output (BACK-893). Not for printing arbitrary values
    extracted *from* a result (e.g. a queried JSON file's own content) —
    those should keep using plain json.dumps/safe_json_dumps directly.

    When provenance is enabled (see set_provenance_enabled), attaches an
    'execution' block to dict results that don't already carry one.
    """
    print(safe_json_dumps(attach_provenance(attach_retirements(attach_input_warnings(result)))), file=file or sys.stdout)
