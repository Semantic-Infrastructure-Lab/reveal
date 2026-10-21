"""--format is honored or rejected, never silently replaced by text (BACK-1425).

`reveal surface://x --format grep` (and calls://, imports://, git://, a
directory listing, most subcommands) printed the text rendering and exited 0,
so a caller asking for grep-able lines got a table it could not parse and no
sign of it. Only overview said so (BACK-1035). An adapter's get_help()
`output_formats` is its declaration; this module enforces it at the routing
seams (URI rendering, adapter-backed subcommands, the directory view).
"""

import logging
import os
import sys
from typing import Any, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_FORMATS: Tuple[str, ...] = ('text', 'json')


def declared_output_formats(adapter_class: Any) -> Optional[Tuple[str, ...]]:
    """The formats an adapter declares in get_help()['output_formats'];
    text and json when it declares none. None when there is no usable
    declaration to enforce (no dict from get_help, e.g. a test double)."""
    get_help = getattr(adapter_class, 'get_help', None)
    if get_help is None:
        return DEFAULT_OUTPUT_FORMATS
    try:
        help_data = get_help()
    except Exception as e:  # boundary-ok: broad-except -- get_help() is adapter code; a broken help dict must not block output and is logged at warning
        logger.warning("%s.get_help() failed (%s); output format not checked",
                       getattr(adapter_class, '__name__', adapter_class), e)
        return None
    if not isinstance(help_data, dict):
        return None
    formats = help_data.get('output_formats')
    if formats is None:
        return DEFAULT_OUTPUT_FORMATS
    return tuple(formats) if isinstance(formats, (list, tuple)) else None


def _require_supported_sinks(args: Any, supported: Sequence[str], label: str) -> None:
    """Exit 2 when a file sink names a format `label` does not render (``--output grep=PATH`` on a
    command that renders text and json): the same check, and the same list, as --format."""
    from ...utils.json_utils import file_sinks
    for fmt, target in file_sinks(args):
        if fmt not in supported:
            print(f"Error: --output {fmt}={target}: {fmt} is not supported by {label} "
                  f"(supported: {', '.join(supported)}).", file=sys.stderr)
            sys.exit(2)


def require_supported_format(args: Any, supported: Optional[Sequence[str]], label: str) -> None:
    """Exit 2 when --format or a file sink names a format `label` does not render.

    A format that came from REVEAL_FORMAT rather than the command line falls
    back to text with a note instead: a session-wide preference should not
    turn every other command into an error.
    """
    if supported is None:
        return
    _require_supported_sinks(args, supported, label)
    fmt = getattr(args, 'format', None) or 'text'
    if fmt in supported:
        return
    if os.environ.get('REVEAL_FORMAT') == fmt and not _format_flag_given():
        print(f"Note: REVEAL_FORMAT={fmt} is not supported by {label}; using text", file=sys.stderr)
        args.format = 'text'
        return
    print(
        f"Error: --format {fmt} is not supported by {label} (supported: {', '.join(supported)}).",
        file=sys.stderr,
    )
    sys.exit(2)


def _format_flag_given() -> bool:
    from ..invocation import current_invocation
    invocation = current_invocation()
    return invocation is not None and invocation.typed('--format')


_SINK_FORMATS = ('text', 'json', 'typed', 'grep')


def _sink_error(message: str) -> None:
    print(f'Error: --output: {message}', file=sys.stderr)  # boundary-ok: print -- the sink usage error line
    sys.exit(2)


def _parse_sinks(specs: Sequence[str]) -> Tuple[list, list]:
    """Split ``--output`` specs into (stdout sinks, file sinks) as (format, path) pairs; exit 2 on a malformed one."""
    stdout_sinks: list = []
    file_sinks: list = []
    for spec in specs:
        fmt, sep, target = spec.partition('=')
        if fmt not in _SINK_FORMATS:
            _sink_error(f"unknown format {fmt!r} in {spec!r}; use one of {', '.join(_SINK_FORMATS)}")
        if sep and not target:
            _sink_error(f'{spec!r} names no PATH; write FORMAT=PATH, or FORMAT alone for stdout')
        (file_sinks if sep else stdout_sinks).append((fmt, target))
    return stdout_sinks, file_sinks


def _stdout_sink(args: Any, invocation: Any, stdout_sinks: list) -> None:
    if len(stdout_sinks) > 1:
        _sink_error('two stdout sinks: '
                    + ' and '.join(f'--output {f}' for f, _ in stdout_sinks) + '; give a path to all but one')
    if stdout_sinks:
        fmt = stdout_sinks[0][0]
        if invocation.typed('--format') and args.format != fmt:
            _sink_error(f'--output {fmt} disagrees with --format {args.format}; they are the same sink')
        args.format = fmt


def _file_sink(args: Any, invocation: Any, file_sinks: list) -> None:
    if file_sinks and (invocation.command == 'check' or getattr(args, 'check', False)):
        other = [f'{f}={t}' for f, t in file_sinks if f != 'json']
        if other:
            _sink_error(f"{', '.join(other)}: check writes only json file sinks; "
                        'its text and grep reports are built per format, so use --output json=PATH')
    if (file_sinks or getattr(args, 'also_json', None)) and getattr(args, 'stdin', False) \
            and not getattr(args, 'check', False):
        _sink_error('a file sink with --stdin needs --check: a list of inputs answers once per input and one '
                    'file holds one result; add --check, or run once per input')
    if file_sinks and getattr(args, 'also_json', None):
        _sink_error('--also-json and --output FORMAT=PATH both name the artifact; use --output FORMAT=PATH only')
    # Left on args.output for the writers (utils.json_utils.file_sinks): the stdout sinks were consumed above.
    args.output = [f'{fmt}={target}' for fmt, target in file_sinks] or None


def apply_output_sinks(args: Any, invocation: Any) -> None:
    """Resolve ``--output FORMAT[=PATH]`` before any scan (BACK-2089 slices 5a, 5b).

    A bare FORMAT is the stdout sink and sets ``args.format``. A ``FORMAT=PATH`` file sink stays on
    ``args.output``, where ``utils.json_utils.file_sinks`` reads it (with ``--also-json``, the retired json
    sink) for whichever writer the command reaches: no writer reads a flag of its own. A bad sink exits 2
    here: an unknown format, an empty PATH, two stdout sinks, a stdout sink that disagrees with a typed
    --format, a non-json file sink on ``check``, a file sink with ``--stdin`` but no ``--check``, or
    ``--also-json`` mixed with a file sink. A format the target does not render is refused where
    --format is (``require_supported_format``). ``--also-json`` alone still works and prints its note.
    """
    from ..invocation import retirement_note
    if invocation.typed('--also-json'):
        retirement_note('flag:--also-json')
    stdout_sinks, file_sinks = _parse_sinks(getattr(args, 'output', None) or ())
    _stdout_sink(args, invocation, stdout_sinks)
    _file_sink(args, invocation, file_sinks)


def _also_json_typed() -> bool:
    from ..invocation import current_invocation
    invocation = current_invocation()
    return invocation is not None and invocation.typed('--also-json')


def reject_unhonored_also_json(args: Any, label: str) -> None:
    """Exit 2 when a file sink (--output FORMAT=PATH, --also-json) was given to an output path that never writes it.

    It is honored by scheme:// URIs (and the file/directory flags that route to
    one), by declared commands and by check; the file view, directory listing, --grep and the other
    subcommands wrote nothing and said nothing (BACK-1425). With --format json
    a json sink is redundant, not unhonored: the primary output already is the JSON.
    """
    from ...utils.json_utils import file_sinks
    sinks = file_sinks(args)
    if getattr(args, 'format', 'text') == 'json':
        sinks = [(fmt, path) for fmt, path in sinks if fmt != 'json']
    if not sinks:
        return
    spelling = '--also-json' if _also_json_typed() else f'--output {sinks[0][0]}=PATH'
    print(
        f"Error: {spelling} is not supported by {label}; it works with scheme:// URIs and "
        "`reveal check`. Use --format json for this command's JSON.",
        file=sys.stderr,
    )
    sys.exit(2)
