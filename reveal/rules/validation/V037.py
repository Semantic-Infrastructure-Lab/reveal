"""
V037: POSIX-only call in a test without a Windows guard.

Flags, in reveal's own tests/, a call or name that does not exist or does not
work on Windows -- ``os.fork``, ``os.getuid``, ``signal.SIGKILL``,
``signal.alarm``, an ``import fcntl``/``pwd``/``resource``, or real I/O on a
hardcoded ``/tmp``, ``/proc`` or ``/dev`` path -- in a module that has no
Windows guard anywhere (``skipif(sys.platform == 'win32')``,
``os.name == 'nt'``, ``hasattr(os, 'fork')``, ``importorskip('fcntl')``).

The local gate runs on Linux, where all of these work, so such a test passes
locally and fails only in the Windows CI job. Paths that are only strings (a
fake root handed to a mocked function, a fixture's source text) are not I/O
and are not flagged; V039 owns path-literal
assertions.

Suppress a reviewed site with ``# noqa: V037 <why>`` on the reported line.

Examples:
    reveal reveal:// --check --select V037
"""

import ast
import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import has_noqa, load_test_suite, parse_test_module

_GUARD_RE = re.compile(
    r'''sys\.platform\s*[!=]=\s*['"]win|sys\.platform\.startswith\(\s*['"]win'''
    r'''|os\.name\s*[!=]=\s*['"]nt['"]|platform\.system\(\)\s*[!=]=\s*['"]Windows'''
    r'''|hasattr\(\s*(?:os|signal)\s*,|importorskip\(\s*['"]''')

# Absent from os/signal on Windows (CPython docs: "Availability: Unix").
_POSIX_OS = frozenset({
    'fork', 'forkpty', 'getuid', 'geteuid', 'getgid', 'getegid', 'getgroups',
    'setuid', 'setgid', 'setsid', 'setpgid', 'getpgid', 'getpgrp', 'setpgrp',
    'killpg', 'mkfifo', 'getloadavg', 'sync', 'wait3', 'wait4', 'WNOHANG', 'nice',
    'chown', 'lchown', 'fchown', 'statvfs', 'sched_getaffinity', 'sched_setaffinity',
})
_POSIX_SIGNAL = frozenset({
    'SIGKILL', 'SIGSTOP', 'SIGCONT', 'SIGHUP', 'SIGQUIT', 'SIGUSR1', 'SIGUSR2',
    'SIGALRM', 'SIGCHLD', 'SIGPIPE', 'SIGTSTP', 'SIGWINCH',
    'alarm', 'setitimer', 'getitimer', 'pause', 'siginterrupt', 'pthread_kill',
    'sigwait', 'ITIMER_REAL',
})
_POSIX_MODULES = frozenset({'pwd', 'grp', 'fcntl', 'termios', 'resource', 'pty', 'tty',
                            'syslog', 'posix'})

# A path under one of these (or the directory itself) is POSIX-only.
_POSIX_ROOTS = ('/tmp/', '/proc/', '/dev/')

# Cheap source pre-filter: only a module that mentions one of the above is parsed.
_HINT_RE = re.compile(
    r'\bos\.(?:%s)\b|\bsignal\.(?:%s)\b|^\s*(?:import|from)\s+(?:%s)\b|[\'"]/(?:%s)\b'
    % ('|'.join(sorted(_POSIX_OS)), '|'.join(sorted(_POSIX_SIGNAL)),
       '|'.join(sorted(_POSIX_MODULES)), '|'.join(r.strip('/') for r in _POSIX_ROOTS)),
    re.MULTILINE)
# Calls whose first argument is a path they read, write or enter.
_IO_FUNCS = frozenset({'open', 'chdir', 'makedirs', 'mkdir', 'listdir', 'scandir', 'walk',
                       'rmtree', 'copy', 'copyfile', 'copytree', 'move', 'remove', 'unlink'})
# Path methods that touch the filesystem (Path('/tmp/x').write_text(...)).
_PATH_IO = frozenset({'write_text', 'write_bytes', 'read_text', 'read_bytes', 'mkdir',
                      'touch', 'open', 'unlink', 'rmdir', 'iterdir'})
_PATH_KEYWORDS = frozenset({'dir', 'cwd'})


def _posix_path(node: Optional[ast.AST]) -> Optional[str]:
    """The literal (or an f-string's literal head) when it names a POSIX-only root."""
    if isinstance(node, ast.JoinedStr) and node.values:
        node = node.values[0]
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        value = node.value
        if (value + '/').startswith(_POSIX_ROOTS):
            return value
    return None


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ''


def _io_on_posix_path(node: ast.Call) -> Optional[str]:
    name = _call_name(node.func)
    if name in _IO_FUNCS and node.args and (path := _posix_path(node.args[0])):
        return f"{name}({path!r})"
    for kw in node.keywords:
        if kw.arg in _PATH_KEYWORDS and (path := _posix_path(kw.value)):
            return f"{kw.arg}={path!r}"
    func = node.func
    if (isinstance(func, ast.Attribute) and func.attr in _PATH_IO
            and isinstance(func.value, ast.Call) and _call_name(func.value.func).endswith('Path')
            and func.value.args and (path := _posix_path(func.value.args[0]))):
        return f"Path({path!r}).{func.attr}()"
    return None


def _posix_uses(tree: ast.Module) -> Iterator[Tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == 'os' and node.attr in _POSIX_OS:
                yield node.lineno, f"os.{node.attr}"
            elif node.value.id == 'signal' and node.attr in _POSIX_SIGNAL:
                yield node.lineno, f"signal.{node.attr}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split('.')[0] in _POSIX_MODULES:
                    yield node.lineno, f"import {alias.name}"
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split('.')[0] in _POSIX_MODULES:
                yield node.lineno, f"from {node.module} import"
        elif isinstance(node, ast.Call) and (what := _io_on_posix_path(node)):
            yield node.lineno, what


class V037(BaseRule):
    """Detect POSIX-only calls in tests that have no Windows guard.

    Severity: MEDIUM -- green on the Linux local gate, red in Windows CI.
    Category: Validation

    Detects:
    - Unix-only ``os``/``signal`` names, Unix-only module imports, and real
      I/O on ``/tmp``, ``/proc``, ``/dev`` paths, in a tests/ module with no
      Windows guard

    Passes:
    - Modules with a Windows guard (skipif on ``sys.platform``, ``os.name``,
      ``hasattr(os, ...)``, ``importorskip``)
    - POSIX paths used only as strings; POSIX calls inside string literals
      (a subprocess driver's source)
    """

    code = "V037"
    message = "POSIX-only call in a test with no Windows guard"
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
        detections: List[Detection] = []
        for display, source in load_test_suite(self):
            if _GUARD_RE.search(source) or not _HINT_RE.search(source):
                continue
            tree = parse_test_module(self, display, source)
            if tree is None:
                continue
            lines = source.splitlines()
            for lineno, what in sorted(set(_posix_uses(tree))):
                line = lines[lineno - 1]
                if has_noqa(line, self.code):
                    continue
                detections.append(self.create_detection(
                    display, lineno,
                    message=f"{what} does not exist or fails on Windows, and this "
                            "module has no Windows guard",
                    suggestion="Add pytest.mark.skipif(sys.platform == 'win32', reason=...) "
                               "to the test (or module), use tempfile/tmp_path for paths, "
                               "or hasattr(os, ...)/importorskip for the capability",
                    context=line.strip(),
                ))
        return detections
