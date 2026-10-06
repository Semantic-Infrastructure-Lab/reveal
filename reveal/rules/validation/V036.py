"""
V036: Fork-dependent test (start-method portability).

Flags a test module that injects behaviour into pool workers the way only a
*forked* worker sees it -- patching a module attribute (``monkeypatch.setattr``,
``mock.patch``) or calling ``os._exit`` -- while running a process pool in the
test process (``ProcessPoolExecutor``/``multiprocessing.Pool``, or reveal's own
pools via ``REVEAL_MAX_WORKERS`` set above 1 or unset), with no start-method
guard anywhere in the module.

A spawned worker (Windows, macOS) or a forkserver one (CPython 3.14+ on Linux)
re-imports the module and never sees the patch, so such a test passes on a
3.12 Linux gate and fails in CI (BACK-1681's tests, fixed by 991424a3). A
guard is a check of the *default* start method (``get_start_method()``,
``needs_forked_workers`` from tests/conftest.py) or an explicit choice
(``get_context('fork')``, ``mp_context=``, ``set_start_method(...)``);
``'fork' in get_all_start_methods()`` is not one --
fork is available on macOS and 3.14 Linux, just not the default.

Suppress a reviewed site with ``# noqa: V036 <why>`` on the reported line.

Examples:
    reveal reveal:// --check --select V036
"""

import ast
import re
from typing import Any, Dict, List, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from .utils import has_noqa, load_test_suite, parse_test_module

# A check of the default start method (tests/conftest.py's needs_forked_workers is
# one), or an explicit one.
_GUARD_RE = re.compile(
    r'''needs_forked_workers|get_start_method\(|set_start_method\(|mp_context\s*='''
    r'''|get_context\(\s*['"]''')

# Cheap source pre-filters: only a module with both is parsed.
_INJECTION_HINT = re.compile(r'_exit\(|setattr\(|patch')
_POOL_HINT = re.compile(r'ProcessPoolExecutor|\bPool\b|REVEAL_MAX_WORKERS|real_worker_pool')

_POOL_NAMES = {'ProcessPoolExecutor', 'Pool'}
_WORKERS_ENV = 'REVEAL_MAX_WORKERS'
# conftest's marker that clears the suite-wide REVEAL_MAX_WORKERS=1.
_POOL_MARKER = 'real_worker_pool'


def _dotted(node: ast.AST) -> str:
    """'a.b.c' for a Name/Attribute chain, else ''."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return '.'.join(reversed(parts))
    return ''


def _str_const(node: Optional[ast.AST]) -> Optional[str]:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _patches_the_pool_itself(node: ast.Call) -> bool:
    """A patch of the pool constructor (a spy or a failing pool) acts in the parent,
    which builds the pool: ``patch.object(mod, 'ProcessPoolExecutor', ...)``,
    ``patch('concurrent.futures.ProcessPoolExecutor')``."""
    return any((_str_const(a) or '').rsplit('.', 1)[-1] in _POOL_NAMES for a in node.args[:2])


def _injection(node: ast.Call) -> str:
    """What a call injects into a worker only fork carries over, or ''."""
    name = _dotted(node.func)
    if name == 'os._exit':
        return 'os._exit()'
    if name == 'monkeypatch.setattr':
        what = 'monkeypatch.setattr()'
    elif name.rsplit('.', 1)[-1] == 'patch' or name.endswith('patch.object'):
        what = f'{name}()'
    else:
        return ''
    return '' if _patches_the_pool_itself(node) else what


def _pools_workers(node: ast.AST) -> bool:
    """A process pool in this process: one named in code, or reveal's own pools given
    more than one worker (REVEAL_MAX_WORKERS set above 1, or unset -- the suite sets 1 --
    directly or by the ``real_worker_pool`` marker)."""
    if isinstance(node, ast.Name) and node.id in _POOL_NAMES:
        return True
    if isinstance(node, ast.Attribute) and node.attr in _POOL_NAMES | {_POOL_MARKER}:
        return True
    if isinstance(node, ast.alias) and node.name in _POOL_NAMES:
        return True
    if isinstance(node, ast.Call) and node.args and _str_const(node.args[0]) == _WORKERS_ENV:
        method = _dotted(node.func).rsplit('.', 1)[-1]
        if method == 'delenv':
            return True
        if method == 'setenv' and len(node.args) > 1:
            return _str_const(node.args[1]) != '1'
    if isinstance(node, ast.Dict):
        return any(_str_const(k) == _WORKERS_ENV and _str_const(v) != '1'
                   for k, v in zip(node.keys, node.values))
    return False


def _injections(node: ast.AST) -> List[Tuple[int, str]]:
    return sorted((n.lineno, what) for n in ast.walk(node)
                  if isinstance(n, ast.Call) and (what := _injection(n)))


class V036(BaseRule):
    """Detect tests whose worker injection only reaches a forked pool worker.

    Severity: MEDIUM -- green on the fork-default local gate, red on Windows,
    macOS and CPython 3.14 Linux CI.
    Category: Validation

    Detects:
    - A tests/ module with module patching or ``os._exit`` AND a process pool
      in the test process AND no start-method guard

    Passes:
    - Modules guarded by ``needs_forked_workers``, ``get_start_method()`` or an
      explicit context
    - Modules that drive the pool in a subprocess (driver source in a string)
    - Patches of the pool constructor itself (a spy or a failing pool)
    """

    code = "V036"
    message = "Fork-dependent test: worker injection without a start-method guard"
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
            if (_GUARD_RE.search(source) or not _INJECTION_HINT.search(source)
                    or not _POOL_HINT.search(source)):
                continue
            tree = parse_test_module(self, display, source)
            detection = tree and self._scan_module(display, source.splitlines(), tree)
            if detection:
                detections.append(detection)
        return detections

    def _scan_module(self, display: str, lines: List[str],
                     tree: ast.Module) -> Optional[Detection]:
        injections = _injections(tree)
        if not injections or not any(_pools_workers(n) for n in ast.walk(tree)):
            return None
        # Module-level: a fixture may patch what a test's pool runs. Report the
        # injection in a function that also runs a pool, else the first one.
        paired = [inj for fn in ast.walk(tree)
                  if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and any(_pools_workers(n) for n in ast.walk(fn))
                  for inj in _injections(fn)]
        lineno, what = min(paired or injections)
        line = lines[lineno - 1]
        if has_noqa(line, self.code):
            return None
        return self.create_detection(
            display, lineno,
            message=f"{what} reaches a pool worker only when it is forked; "
                    "spawn (Windows, macOS) and forkserver (py3.14 Linux) workers re-import",
            suggestion="Mark the test @needs_forked_workers (tests/conftest.py), or drive "
                       "the pool in a subprocess with an injection that works under every "
                       "start method (tests/test_pool_start_methods_back1704.py)",
            context=line.strip(),
        )
