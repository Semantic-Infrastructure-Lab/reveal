"""
V041: Text-mode file I/O without an explicit ``encoding=`` (the Windows cp1252 ratchet).

On Windows the default text encoding is cp1252, not UTF-8, so a bare
``Path.read_text()`` / ``open(p)`` that touches a non-ASCII file raises
UnicodeDecodeError there while passing on Linux/macOS (BACK-1346/1347 CI:
tests/test_surface_matrix.py read scanner source without an encoding).

This is ``scripts/check_text_encoding.py`` (BACK-1354) moved into the V-series
(BACK-1707): same call classification, same ratchet, same findings. It scans
``reveal/``, ``tests/`` and ``scripts/``:

* STRICT class, never baselined: in ``tests/``, a bare read/open whose path derives from
  ``__file__`` or an UPPERCASE module constant (repo sources, docs, fixtures). Those files
  hold non-ASCII text and are what broke Windows CI. Every site is reported.
* Everything else is a ratchet against ``scripts/text_encoding_baseline.json`` (per-file
  counts of legacy offenders): a file may stay at or below its baseline; a file above it
  (or absent from it) is reported at every bare site, since a count cannot say which is new.
  The baseline may only fall: ``python scripts/check_text_encoding.py --update-baseline``
  rewrites it after sites are fixed, and refuses while a STRICT site exists.

Flagged: ``open`` / ``io.open`` / ``Path.open`` / ``read_text`` / ``write_text`` in text mode,
``tempfile.NamedTemporaryFile``-family in text mode, and ``subprocess`` calls with
``text=True`` / ``universal_newlines=True`` / ``errors=`` but no ``encoding=`` (they decode
with cp1252 on Windows). ``**kwargs`` is trusted (unknowable). Not checked: stdout/stderr
(see ``reveal.main._setup_console``) and aliased ``open`` (``o = open``).

Fix a site with ``encoding='utf-8'`` (or ``'rb'`` mode). Suppress a false positive with
``# noqa: text-encoding`` (the spelling the repo already uses) or ``# noqa: V041`` on the
call line.

Local repro of the failure class on Linux (ASCII locale):
    PYTHONUTF8=0 PYTHONCOERCECLOCALE=0 LC_ALL=C pytest tests/<file>

Examples:
    reveal reveal:// --check --select V041
"""

import ast
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import find_reveal_root, has_noqa, load_sources
from reveal.utils.lines import split_lines

TREES = ('reveal', 'tests', 'scripts')
BASELINE_REL = 'scripts/text_encoding_baseline.json'

NOT_FILES = {'os', 'io', 'webbrowser', 'gzip', 'zipfile', 'tarfile', 'urllib', 'codecs',
             'subprocess', 'opener', 'dist', 'session', 'client'}
TEMPFILES = {'NamedTemporaryFile', 'TemporaryFile', 'SpooledTemporaryFile'}
SUBPROCESS_FUNCS = {'run', 'Popen', 'check_output', 'check_call', 'call'}


def _mode(call: ast.Call, positional: list[ast.expr]):
    for kw in call.keywords:
        if kw.arg == 'mode' and isinstance(kw.value, ast.Constant):
            return kw.value.value
    if positional and isinstance(positional[0], ast.Constant):
        return positional[0].value
    return None


def _kw(call: ast.Call, name: str):
    return next((kw for kw in call.keywords if kw.arg == name), None)


def _has_encoding(call: ast.Call, positional_index: int | None = None) -> bool:
    """True if an encoding is given (keyword, ``**kwargs`` we cannot see, or positional)."""
    if any(kw.arg is None for kw in call.keywords):
        return True
    kw = _kw(call, 'encoding')
    if kw is not None:
        return not (isinstance(kw.value, ast.Constant) and kw.value.value is None)
    return positional_index is not None and len(call.args) > positional_index


def _is_text_mode(mode) -> bool:
    return not (isinstance(mode, str) and 'b' in mode)


def _is_bare_attr_open(owner: str | None, call: ast.Call) -> bool:
    """``x.open(...)`` / ``io.open(...)`` in text mode with no encoding."""
    if owner in NOT_FILES and owner != 'io':
        return False
    return _is_text_mode(_mode(call, call.args[0:1])) and not _has_encoding(call)


def _is_bare_tempfile(call: ast.Call) -> bool:
    mode = _mode(call, call.args[0:1])
    return isinstance(mode, str) and _is_text_mode(mode) and not _has_encoding(call)


def _is_bare_subprocess(call: ast.Call) -> bool:
    """A subprocess call that decodes text (text=True, universal_newlines=True, errors=)
    but names no encoding: cp1252 on Windows."""
    textual = any(
        (kw := _kw(call, name)) is not None and not (isinstance(kw.value, ast.Constant) and not kw.value.value)
        for name in ('text', 'universal_newlines', 'errors')
    )
    return textual and not _has_encoding(call)


def is_bare_text_io(call: ast.Call) -> bool:
    func = call.func
    attr = func.attr if isinstance(func, ast.Attribute) else None
    owner = func.value.id if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) else None
    if attr == 'read_text':
        return owner not in NOT_FILES and not _has_encoding(call, 0)
    if attr == 'write_text':
        return owner not in NOT_FILES and not _has_encoding(call, 1)
    if isinstance(func, ast.Name) and func.id == 'open':
        return _is_text_mode(_mode(call, call.args[1:2])) and not _has_encoding(call)
    if attr == 'open':
        return _is_bare_attr_open(owner, call)
    if (attr or getattr(func, 'id', None)) in TEMPFILES:
        return _is_bare_tempfile(call)
    if owner == 'subprocess' and attr in SUBPROCESS_FUNCS:
        return _is_bare_subprocess(call)
    return False


def is_strict_site(call: ast.Call) -> bool:
    """A repo-file read: the path derives from __file__ or an UPPERCASE constant."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr in ('read_text', 'open', 'write_text'):
        target: ast.AST = func.value
    elif isinstance(func, ast.Name) and func.id == 'open' and call.args:
        target = call.args[0]
    else:
        return False
    names = {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}
    return '__file__' in names or any(n.isupper() and len(n) > 2 for n in names)


def find_bare_text_io(tree: ast.Module, lines: List[str],
                      in_tests: bool) -> Tuple[List[int], List[int]]:
    """(legacy lines, STRICT lines) of the bare text I/O calls in one parsed module.
    STRICT only applies in tests/ (`in_tests`); a ``noqa: text-encoding``/``V041`` line
    is skipped."""
    found: List[int] = []
    strict: List[int] = []
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and is_bare_text_io(n)):
            continue
        line = lines[n.lineno - 1]
        if 'noqa: text-encoding' in line or has_noqa(line, 'V041'):
            continue
        (strict if in_tests and is_strict_site(n) else found).append(n.lineno)
    return sorted(found), sorted(strict)


def scan_modules(modules: Iterable[Tuple[str, str]],
                 unparsed: Optional[List[Tuple[str, str]]] = None,
                 ) -> Tuple[Dict[str, List[int]], Dict[str, List[int]]]:
    """(legacy, strict): file -> lines, over (display path, source) modules. A module that
    does not parse is appended to *unparsed* (when given) as (display, error)."""
    found: Dict[str, List[int]] = {}
    strict: Dict[str, List[int]] = {}
    for display, source in modules:
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError) as e:
            if unparsed is not None:
                unparsed.append((display, f"{type(e).__name__}: {e}"))
            continue
        legacy, strict_lines = find_bare_text_io(
            tree, split_lines(source), display.startswith('tests/'))
        if legacy:
            found[display] = legacy
        if strict_lines:
            strict[display] = strict_lines
    return found, strict


def regressions(found: Dict[str, List[int]],
                baseline: Dict[str, int]) -> Dict[str, Tuple[int, int]]:
    """file -> (baseline count, now) for each file above its baseline (absent = 0)."""
    return {f: (baseline.get(f, 0), len(v)) for f, v in found.items()
            if len(v) > baseline.get(f, 0)}


def load_baseline(root: Path) -> Dict[str, int]:
    """The per-file legacy counts under *root*; empty when the file does not exist."""
    path = root / BASELINE_REL
    if not path.exists():
        return {}
    counts: Dict[str, int] = json.loads(path.read_text(encoding='utf-8'))
    return counts


class V041(BaseRule):
    """Detect text-mode file I/O without ``encoding=`` (breaks on Windows cp1252).

    Severity: MEDIUM -- green on Linux and macOS, red in Windows CI.
    Category: Validation

    Detects (in ``reveal/``, ``tests/``, ``scripts/``):
    - a bare text-mode ``open``/``read_text``/``write_text``/tempfile/``subprocess(text=True)``
      that reads a repo file in ``tests/`` (STRICT: always reported), or that raises a
      file's count above ``scripts/text_encoding_baseline.json`` (ratchet)

    Passes:
    - ``encoding=`` given, binary mode, ``**kwargs``; files at or under their baseline
    - ``# noqa: text-encoding`` (or ``# noqa: V041``) lines
    """

    code = "V041"
    message = "Text I/O without encoding= (breaks on Windows cp1252)"
    category = RulePrefix.V
    severity = Severity.MEDIUM
    file_patterns = ['.py']
    uri_patterns = ['^reveal://.*']
    internal = True
    version = "1.0.0"

    def check(self,
              file_path: str,
              structure: Optional[Dict[str, Any]],
              content: str) -> List[Detection]:
        if not file_path.startswith('reveal://'):
            return []
        modules = load_sources(self, TREES, lambda path: True)
        if not modules:
            return []
        unparsed: List[Tuple[str, str]] = []
        found, strict = scan_modules(modules, unparsed)
        for display, error in unparsed:
            self.unavailable(error, display)
        reveal_root = find_reveal_root()
        baseline = load_baseline(reveal_root.parent) if reveal_root else {}
        sources = dict(modules)
        detections: List[Detection] = []

        def add(display: str, lineno: int, why: str) -> None:
            detections.append(self.create_detection(
                display, lineno,
                message=f"Text I/O without encoding= (breaks on Windows cp1252): {why}",
                suggestion="Pass encoding='utf-8' (or use binary mode); suppress a "
                           "reviewed false positive with # noqa: text-encoding",
                context=split_lines(sources[display])[lineno - 1].strip(),
            ))

        for display in sorted(strict):
            for lineno in strict[display]:
                add(display, lineno, "STRICT: reads a repo file/fixture, never baselined")
        for display, (was, now) in sorted(regressions(found, baseline).items()):
            for lineno in found[display]:
                add(display, lineno,
                    f"ratchet: {display} went {was} -> {now} bare sites over its baseline")
        return detections
