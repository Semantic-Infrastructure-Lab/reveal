"""Read a named setting for the parse-count qualification corpus."""
import os


def configured_name(fallback):
    """Return an explicit setting or the caller's fallback."""
    return os.environ.get('REVEAL_PARSE_GATE_NAME', fallback)
