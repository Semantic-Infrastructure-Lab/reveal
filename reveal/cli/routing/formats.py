"""--format is honored or rejected, never silently replaced by text (BACK-1425).

`reveal surface://x --format grep` (and calls://, imports://, git://, a
directory listing, most subcommands) printed the text rendering and exited 0,
so a caller asking for grep-able lines got a table it could not parse and no
sign of it. Only overview said so (BACK-1035). An adapter's get_help()
`output_formats` is its declaration; this module enforces it at the routing
seams (URI rendering, adapter-backed subcommands, the directory view).
"""

import os
import sys
from typing import Any, Optional, Sequence, Tuple

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
    except Exception:  # noqa: BLE001 -- a broken help dict must not block output
        return None
    if not isinstance(help_data, dict):
        return None
    formats = help_data.get('output_formats')
    if formats is None:
        return DEFAULT_OUTPUT_FORMATS
    return tuple(formats) if isinstance(formats, (list, tuple)) else None


def require_supported_format(args: Any, supported: Optional[Sequence[str]], label: str) -> None:
    """Exit 2 when --format names a format `label` does not render.

    A format that came from REVEAL_FORMAT rather than the command line falls
    back to text with a note instead: a session-wide preference should not
    turn every other command into an error.
    """
    if supported is None:
        return
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
    return any(arg == '--format' or arg.startswith('--format=') for arg in sys.argv[1:])


def reject_unhonored_also_json(args: Any, label: str) -> None:
    """Exit 2 when --also-json was given to an output path that never writes it.

    It is honored by scheme:// URIs (and the file/directory flags that route to
    one) and by check; the file view, directory listing, --grep and the other
    subcommands wrote nothing and said nothing (BACK-1425). With --format json
    the primary output already is the JSON, so the flag is redundant there,
    not unhonored.
    """
    if not getattr(args, 'also_json', None) or getattr(args, 'format', 'text') == 'json':
        return
    print(
        f"Error: --also-json is not supported by {label}; it works with scheme:// URIs and "
        "`reveal check`. Use --format json for this command's JSON.",
        file=sys.stderr,
    )
    sys.exit(2)
