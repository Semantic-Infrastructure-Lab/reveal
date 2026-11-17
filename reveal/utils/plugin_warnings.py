"""Code reveal loads from the user's or project's directories that did not load as written.

An analyzer plugin, an adapter plugin or a rule module that raised on import, a rule module without
its rule class, a rule with an unknown severity and the legacy rules directory are each a
``meta.warnings`` entry of type ``plugin_warning`` (BACK-2659), recorded in the running invocation
like a ``config_warning``: the answer carries it, and it never changes the exit code or the
answer's completeness. Plugins load once per process, so a discovery keeps what it met in a
``DiscoveryNotes`` and every later discovery call replays it into the invocation that makes it (an
MCP server reports a broken plugin on every request, not only the first).
"""

import logging
from typing import Any, Dict, List, Tuple

from .invocation_log import record_warning

PLUGIN_WARNING = 'plugin_warning'


def plugin_warning(code: str, message: str, **fields: Any) -> Dict[str, Any]:
    """A ``plugin_warning`` entry: ``plugin_load_failed`` (``path``, ``kind``, ``reason``),
    ``rule_class_missing`` (``path``, ``rule``), ``rule_severity_unknown`` (``rule``, ``severity``)
    or ``rules_dir_legacy`` (``path``, ``replacement``)."""
    return {'type': PLUGIN_WARNING, 'code': code, 'message': message, **fields}


class DiscoveryNotes:
    """What one discovery met, replayed into each invocation that discovers again."""

    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger
        self._notes: List[Tuple[Dict[str, Any], int, str, Tuple[Any, ...]]] = []

    def note(self, entry: Dict[str, Any], level: int, log_format: str, *log_args: Any) -> None:
        """Keep *entry* and record it in the running invocation; outside one (a plain library call)
        log it instead, as before."""
        self._notes.append((entry, level, log_format, log_args))
        if not record_warning(entry):
            self._logger.log(level, log_format, *log_args)

    def replay(self) -> None:
        """Record what the discovery met in the running invocation (once per invocation)."""
        for entry, _level, _format, _args in self._notes:
            record_warning(entry)

    def clear(self) -> None:
        """A new discovery starts: what the previous one met no longer holds."""
        self._notes.clear()
