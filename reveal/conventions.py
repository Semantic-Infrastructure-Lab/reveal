"""Per-language conventions: what each language treats as implicit, builtin, or a test.

Reveal's syntactic layer is language-neutral (one node taxonomy, one extension
router). What is NOT neutral is *convention* knowledge -- which functions a
runtime or test runner invokes without a call expression, which callee names
are builtins, what a test looks like. That knowledge used to live as
``== 'python'`` branches and module-level sets scattered across adapters
(BACK-1272 review, Part 2 P1-P5). This module is its single home: adapters ask
``conventions_for(family)`` instead of branching on a language name.

Keyed by the coarse *family* slug that ``calls://`` already uses (``python``,
``js`` for JS/TS/TSX, ``c`` for C/C++, ...), because conventions are shared
across a family's dialects. An unregistered family gets the EMPTY profile, so
"no conventions known" reads as "exclude nothing", never as Python's rules.

Fields exist only where an adapter consumes them today. Doc-comment style is
deliberately not stubbed in yet.
"""

import builtins as _builtins_module
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, FrozenSet, Optional, Pattern, Tuple

from .registry import language_for_extension

# Tree-sitter language slug -> coarse family, for scoping callee resolution and
# conventions to the caller's language (BACK-405). C/C++ share one family since
# headers (.h) are ambiguous between the two and target one symbol namespace.
# Extension->language identity is NOT re-declared here -- it is looked up from
# the registry (BACK-431 Issue B), so a new extension routed to an existing
# language is automatically in-family.
FAMILY_BY_LANGUAGE: Dict[str, str] = {
    'c': 'c', 'cpp': 'c',
    'python': 'python',
    'javascript': 'js', 'typescript': 'js', 'tsx': 'js',
    'go': 'go',
    'rust': 'rust',
    'java': 'java',
    'csharp': 'csharp',
    'ruby': 'ruby',
    'php': 'php',
    'kotlin': 'kotlin',
    'swift': 'swift',
    'scala': 'scala',
    'lua': 'lua',
    'dart': 'dart',
}

# All public names in the Python builtins module. Built at import time so it
# stays in sync with the running Python version.
PYTHON_BUILTINS: FrozenSet[str] = frozenset(
    name for name in dir(_builtins_module) if not name.startswith('_')
)


@dataclass(frozen=True)
class LanguageConventions:
    """What one language family invokes implicitly, treats as builtin, or calls a test."""

    family: str
    # Callee names that are language builtins; hidden from calls lists by default.
    # Scoped per family because the names collide with real methods elsewhere
    # (Python `map`/`filter` vs Scala/Ruby `.map`/`.filter`, BACK-748).
    builtins: FrozenSet[str] = frozenset()
    # Decorators/annotations that make the runtime dispatch a function implicitly.
    implicit_decorators: FrozenSet[str] = frozenset()
    # Framework route/handler/scheduler decorators (bare names, case-sensitive) that
    # register a function with a framework; it is invoked by dispatch, not a call.
    entry_point_decorators: FrozenSet[str] = frozenset()
    # Definition names invoked by the language/runtime, never by a call expression.
    implicit_names: FrozenSet[str] = frozenset()
    # Same, by pattern (Python `__dunder__`).
    implicit_name_pattern: Optional[Pattern[str]] = None
    # Decorators that mark a test-runner entry point and are captured as `decorators`.
    test_decorators: FrozenSet[str] = frozenset()
    # Name conventions a test runner collects without an explicit call.
    test_name_prefixes: Tuple[str, ...] = ()
    # JUnit3-style `testXxx` is only a test inside a test file; a bare `test*`
    # elsewhere is an ordinary method, and hiding it would hide real dead code.
    test_prefixes_in_test_files_only: bool = False
    test_lifecycle_names: FrozenSet[str] = frozenset()
    # Pattern-based test names (Go `TestXxx`), optionally only in files ending in
    # one of `test_file_suffixes` (Go requires `_test.go`; empty = any file).
    test_name_pattern: Optional[Pattern[str]] = None
    test_file_suffixes: Tuple[str, ...] = ()
    # Source-text markers for test attributes/annotations (`[Fact]`, `@Test`).
    # Used where the marker is not (reliably) captured as a decorator.
    test_annotation_markers: Tuple[str, ...] = ()
    # Maps a raw (non-relative) import string to its stdlib package key, or None
    # when it is not stdlib. None here = no reliable stdlib rule for the language,
    # so nothing is claimed stdlib (BACK-1193: never fall back to Python's list).
    stdlib_key: Optional[Callable[[str], Optional[str]]] = None
    # How to find which names the tests cover (hotspots `has_test_hint`, BACK-1276).
    # Basename patterns for test files (group 1 = the module under test), and
    # source patterns (MULTILINE, group 1 = the name under test) applied to test
    # files. `colocated_test_symbols`: tests live inline in ordinary source files
    # (Rust `#[cfg(test)]`), so symbol patterns run on every file of the family.
    # No patterns = no way to tell, which callers must report as unknown, not "untested".
    test_file_patterns: Tuple[Pattern[str], ...] = ()
    test_symbol_patterns: Tuple[Pattern[str], ...] = ()
    colocated_test_symbols: bool = False
    # Exact basenames that are test infrastructure though no pattern matches (`conftest.py`).
    test_file_names: FrozenSet[str] = frozenset()
    # Lowercase basenames a runtime/build tool starts from (pack's entry-point bonus,
    # BACK-1287), and files that only re-export (barrels), excluded from "core
    # abstractions" rankings in architecture://.
    entry_point_files: FrozenSet[str] = frozenset()
    reexport_files: FrozenSet[str] = frozenset()

    def is_test_basename(self, name: str) -> bool:
        """True if file *name* is a test file by this family's own naming convention."""
        return name in self.test_file_names or any(p.match(name) for p in self.test_file_patterns)

    @property
    def has_test_index(self) -> bool:
        """True if this family has any rule for attributing tests to names."""
        return bool(self.test_file_patterns or self.test_symbol_patterns)

    def is_implicit_name(self, name: str) -> bool:
        """True if *name* is invoked by the language/runtime rather than called."""
        if name in self.implicit_names:
            return True
        return bool(self.implicit_name_pattern and self.implicit_name_pattern.match(name))

    def is_test_name(self, name: str, file_path: str = '') -> bool:
        """True if *name* follows this language's test-runner naming convention.

        *file_path* matters only for languages whose convention is file-scoped
        (Go): a `TestFoo` outside a `_test.go` file is an ordinary function.
        """
        if name in self.test_lifecycle_names:
            return True
        if self.test_name_prefixes and name.startswith(self.test_name_prefixes):
            if not self.test_prefixes_in_test_files_only:
                return True
            from .utils.path_utils import is_test_path  # lazy: path_utils imports this module
            return is_test_path(file_path)
        if self.test_name_pattern and self.test_name_pattern.match(name):
            return not self.test_file_suffixes or file_path.endswith(self.test_file_suffixes)
        return False


# Framework entry-point decorators, by ecosystem (BACK-1265, BACK-1273).
# Python: HTTP verbs (FastAPI, Flask, Sanic, Starlette, aiohttp, Bottle), error/lifecycle
# handlers, CLI (Click, Typer), task queues (Celery, RQ, Huey, APScheduler), event/signal
# dispatch, BDD step registration. Rust attribute macros (actix/rocket `#[get("/")]`) share
# the lowercase verb spelling.
PYTHON_ENTRY_POINT_DECORATORS: FrozenSet[str] = frozenset({
    'get', 'post', 'put', 'patch', 'delete', 'head', 'options',
    'route', 'websocket', 'websocket_route',
    'exception_handler', 'errorhandler', 'middleware', 'on_event',
    'before_request', 'after_request', 'teardown_request',
    'before_app_request', 'app_errorhandler',
    'command', 'group', 'callback',
    'task', 'shared_task', 'periodic_task', 'scheduled_job',
    'listener', 'subscribe', 'receiver', 'event', 'on', 'hook',
    'given', 'when', 'then', 'step', 'fixture',
})
# NestJS/Angular: decorators are PascalCase, so the lowercase Python list never matched.
JS_ENTRY_POINT_DECORATORS: FrozenSet[str] = frozenset({
    'Get', 'Post', 'Put', 'Patch', 'Delete', 'Head', 'Options', 'All',
    'Query', 'Mutation', 'Subscription', 'ResolveField',
    'MessagePattern', 'EventPattern', 'SubscribeMessage', 'OnEvent',
    'Cron', 'Interval', 'Timeout', 'Process', 'HostListener',
})
# Spring, JAX-RS, Jakarta lifecycle, and `@Override` (reached through the overridden type).
JVM_ENTRY_POINT_DECORATORS: FrozenSet[str] = frozenset({
    'RequestMapping', 'GetMapping', 'PostMapping', 'PutMapping', 'PatchMapping',
    'DeleteMapping', 'ExceptionHandler', 'ModelAttribute', 'InitBinder',
    'Bean', 'Scheduled', 'EventListener', 'TransactionalEventListener',
    'KafkaListener', 'RabbitListener', 'JmsListener',
    'PostConstruct', 'PreDestroy', 'Override',
    'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS',
    # Dagger/Hilt: module methods are called by generated component code (BACK-1392).
    'Provides', 'Binds', 'BindsInstance', 'BindsOptionalOf', 'Multibinds',
})
# ASP.NET Core actions/routes and Azure Functions, as captured `[Attr(...)]` names (BACK-1392).
CSHARP_ENTRY_POINT_DECORATORS: FrozenSet[str] = frozenset({
    'HttpGet', 'HttpPost', 'HttpPut', 'HttpPatch', 'HttpDelete', 'HttpHead', 'HttpOptions',
    'Route', 'AcceptVerbs', 'FunctionName', 'Function',
})

# --- stdlib classification (BACK-1275) --------------------------------------

# Python 3.10+ ships sys.stdlib_module_names; the fallback set covers older
# interpreters.
PYTHON_STDLIB: FrozenSet[str] = frozenset(getattr(sys, 'stdlib_module_names', ())) | frozenset({
    'abc', 'ast', 'asyncio', 'builtins', 'collections', 'contextlib',
    'copy', 'dataclasses', 'datetime', 'enum', 'functools', 'gc',
    'glob', 'hashlib', 'http', 'importlib', 'inspect', 'io', 'itertools',
    'json', 'logging', 'math', 'multiprocessing', 'operator', 'os',
    'pathlib', 'pickle', 'platform', 're', 'shutil', 'signal', 'socket',
    'sqlite3', 'string', 'struct', 'subprocess', 'sys', 'tempfile',
    'threading', 'time', 'traceback', 'typing', 'unittest', 'urllib',
    'uuid', 'warnings', 'weakref', 'zipfile', 'zlib',
})

# Go's standard library is a closed set of top-level path elements. "First
# element has no dot" would also swallow dotless local module paths
# (`myapp/pkg`), so the closed list is used instead.
GO_STDLIB_ROOTS: FrozenSet[str] = frozenset({
    'archive', 'bufio', 'bytes', 'cmp', 'compress', 'container', 'context',
    'crypto', 'database', 'debug', 'embed', 'encoding', 'errors', 'expvar',
    'flag', 'fmt', 'go', 'hash', 'html', 'image', 'index', 'io', 'iter', 'log',
    'maps', 'math', 'mime', 'net', 'os', 'path', 'plugin', 'reflect', 'regexp',
    'runtime', 'slices', 'sort', 'strconv', 'strings', 'structs', 'sync',
    'syscall', 'testing', 'text', 'time', 'unicode', 'unique', 'unsafe', 'weak',
})

NODE_BUILTINS: FrozenSet[str] = frozenset({
    'assert', 'async_hooks', 'buffer', 'child_process', 'cluster', 'console',
    'constants', 'crypto', 'dgram', 'diagnostics_channel', 'dns', 'domain',
    'events', 'fs', 'http', 'http2', 'https', 'inspector', 'module', 'net',
    'os', 'path', 'perf_hooks', 'process', 'punycode', 'querystring',
    'readline', 'repl', 'stream', 'string_decoder', 'sys', 'timers', 'tls',
    'trace_events', 'tty', 'url', 'util', 'v8', 'vm', 'wasi', 'worker_threads',
    'zlib',
})


def _python_stdlib_key(module: str) -> Optional[str]:
    top = module.split('.')[0]
    return top if top in PYTHON_STDLIB else None


def _go_stdlib_key(module: str) -> Optional[str]:
    return module if module.split('/')[0] in GO_STDLIB_ROOTS else None


def _rust_stdlib_key(module: str) -> Optional[str]:
    top = module.split('::')[0].strip()
    return top if top in {'std', 'core', 'alloc'} else None


def _prefix_stdlib_key(*roots: str) -> Callable[[str], Optional[str]]:
    """Dotted-namespace stdlib (Java `java.util.List`): key is the root segment."""
    def key(module: str) -> Optional[str]:
        top = module.split('.')[0]
        return top if top in roots else None
    return key


def _node_stdlib_key(module: str) -> Optional[str]:
    if module.startswith('node:'):  # syntactic marker, no list needed
        return module[len('node:'):].split('/')[0]
    top = module.split('/')[0]
    return top if top in NODE_BUILTINS else None


EMPTY = LanguageConventions(family='')

# Attribute/annotation markers a structure pass does not surface as `decorators`
# for C# and the JVM languages (BACK-446). Matched by a scoped source scan.
_CSHARP_TEST_MARKERS: Tuple[str, ...] = (
    '[Fact', '[Theory', '[Test', '[SetUp', '[TearDown',
    '[OneTimeSetUp', '[OneTimeTearDown',
)
_JVM_TEST_MARKERS: Tuple[str, ...] = (
    '@Test', '@ParameterizedTest', '@RepeatedTest', '@TestFactory',
    '@BeforeEach', '@AfterEach', '@BeforeAll', '@AfterAll',
    '@Before', '@After', '@BeforeClass', '@AfterClass',
)

_CONVENTIONS: Dict[str, LanguageConventions] = {
    c.family: c for c in (
        LanguageConventions(
            family='python',
            entry_point_files=frozenset({
                'main.py', 'app.py', 'server.py', 'index.py', 'cli.py', 'run.py',
                'wsgi.py', 'asgi.py', '__main__.py',
            }),
            reexport_files=frozenset({'__init__.py'}),
            stdlib_key=_python_stdlib_key,
            test_file_patterns=(re.compile(r'^test_(.+)\.py$'), re.compile(r'^(.+)_test\.py$')),
            test_file_names=frozenset({'conftest.py'}),
            test_symbol_patterns=(
                re.compile(r'^\s*(?:async\s+)?def\s+test_(\w+)', re.MULTILINE),
                re.compile(r'^\s*class\s+Test(\w+)', re.MULTILINE),
            ),
            builtins=PYTHON_BUILTINS,
            implicit_decorators=frozenset({'property', 'classmethod', 'staticmethod'}),
            entry_point_decorators=PYTHON_ENTRY_POINT_DECORATORS,
            implicit_name_pattern=re.compile(r'^__.*__$'),
            test_decorators=frozenset({'fixture'}),
            test_name_prefixes=('test_',),
            test_lifecycle_names=frozenset({
                'setUp', 'tearDown', 'setUpClass', 'tearDownClass',
                'setUpModule', 'tearDownModule',
            }),
        ),
        # JS/TS `new ClassName(...)` indexes under "ClassName" while the method
        # definition is literally `constructor`, so the names never match
        # (BACK-1009: 18.5% of ?uncalled hits on the VS Code corpus).
        LanguageConventions(
            family='js', implicit_names=frozenset({'constructor'}), stdlib_key=_node_stdlib_key,
            entry_point_files=frozenset({
                'main.js', 'index.js', 'app.js', 'server.js',
                'main.ts', 'index.ts', 'app.ts', 'server.ts',
            }),
            reexport_files=frozenset({
                'index.js', 'index.jsx', 'index.mjs', 'index.ts', 'index.tsx',
            }),
            entry_point_decorators=JS_ENTRY_POINT_DECORATORS,
            # Jest/Vitest/Mocha test titles are free text, so only the file name is a signal.
            test_file_patterns=(re.compile(r'^(.+)\.(?:test|spec)\.[cm]?[jt]sx?$'),),
        ),
        # BACK-1197: `initialize` is invoked by .new; the rest are Module/Class
        # hook callbacks and metaprogramming dispatch.
        LanguageConventions(
            family='ruby',
            entry_point_files=frozenset({'main.rb', 'config.ru'}),
            implicit_names=frozenset({
                'initialize', 'included', 'extended', 'inherited',
                'method_missing', 'respond_to_missing?',
            }),
            test_file_patterns=(re.compile(r'^(.+)_(?:spec|test)\.rb$'),),
            test_file_names=frozenset({'spec_helper.rb'}),
        ),
        # `main` and `init` are run by the runtime. `go test` collects
        # Test/Benchmark/Example/Fuzz functions in _test.go files; the name after
        # the prefix must not start with a lowercase letter (`Testable` is not a test).
        LanguageConventions(
            family='go',
            entry_point_files=frozenset({'main.go'}),
            reexport_files=frozenset({'doc.go'}),
            stdlib_key=_go_stdlib_key,
            test_file_patterns=(re.compile(r'^(.+)_test\.go$'),),
            test_symbol_patterns=(
                re.compile(r'^func\s+(?:Test|Benchmark|Example|Fuzz)(\w+)', re.MULTILINE),
            ),
            implicit_names=frozenset({'main', 'init'}),
            test_name_pattern=re.compile(r'^(Test|Benchmark|Example|Fuzz)(?![a-z])'),
            test_file_suffixes=('_test.go',),
        ),
        # `#[test]`-family attributes are captured as decorators (raw `#[...]` text,
        # reduced to the bare last path segment by the calls adapter).
        LanguageConventions(
            family='rust',
            entry_point_files=frozenset({'main.rs', 'lib.rs'}),
            reexport_files=frozenset({'mod.rs'}),
            entry_point_decorators=PYTHON_ENTRY_POINT_DECORATORS,
            stdlib_key=_rust_stdlib_key,
            test_symbol_patterns=(re.compile(
                r'#\[(?:\w+::)?(?:test|rstest)\b[^\]]*\]\s*(?:#\[[^\]]*\]\s*)*(?:async\s+)?fn\s+(?:test_)?(\w+)'
            ),),
            colocated_test_symbols=True,
            test_file_patterns=(re.compile(r'^(.+)_tests\.rs$'),),
            test_file_names=frozenset({'tests.rs'}),
            implicit_names=frozenset({'main'}),
            test_decorators=frozenset({'test', 'bench', 'rstest'}),
        ),
        # C++ operators run from expression syntax (`a == b`) and destructors at
        # scope exit, never by a call to their name; an out-of-line constructor
        # (`Foo::Foo`) is reached by `Foo(...)`/declaration, which indexes as `Foo`.
        LanguageConventions(
            family='c',
            entry_point_files=frozenset({'main.c', 'main.cpp', 'main.cc'}),
            # Any extension: the family is already chosen by extension via the
            # registry, and a re-listed set here missed .h++ (BACK-1255).
            test_file_patterns=(re.compile(r'^(.+)_tests\.[^.]+$'),),
            implicit_names=frozenset({'main'}),
            implicit_name_pattern=re.compile(
                r'^(?:.*::)?(?:operator\b.*|~\w+)$'  # operators, destructors
                r'|^(?:.*::)?(\w+)::\1$'  # out-of-line constructor Foo::Foo
            ),
            # Test-registration macros (GoogleTest, Catch2/doctest, Boost.Test) parse as a
            # function named after the macro; gtest fixture hooks are virtual overrides.
            test_lifecycle_names=frozenset({
                'TEST', 'TEST_F', 'TEST_P', 'TYPED_TEST', 'TYPED_TEST_P',
                'TEST_CASE', 'TEST_CASE_METHOD', 'SCENARIO', 'TEMPLATE_TEST_CASE',
                'BOOST_AUTO_TEST_CASE', 'BOOST_FIXTURE_TEST_CASE',
                'SetUp', 'TearDown', 'SetUpTestSuite', 'TearDownTestSuite',
            }),
        ),
        # BACK-1443: magic methods run on `new`/`clone`/serialize/property access/an
        # undefined-method call, never by a call to their name. An exact list, not a
        # `__` pattern: WordPress defines ordinary functions named `__return_null`,
        # `__ngettext` (passed as hook-string callbacks) that must stay checkable.
        LanguageConventions(
            family='php', entry_point_files=frozenset({'index.php'}),
            implicit_names=frozenset({
                '__construct', '__destruct', '__call', '__callStatic', '__get', '__set',
                '__isset', '__unset', '__sleep', '__wakeup', '__serialize', '__unserialize',
                '__toString', '__invoke', '__set_state', '__clone', '__debugInfo',
            }),
        ),
        LanguageConventions(
            family='swift', entry_point_files=frozenset({'main.swift'}),
            # `P(x:)` indexes under the type name, never `init`; operators run on `a == b`.
            implicit_names=frozenset({'init', 'deinit'}),
            implicit_name_pattern=re.compile(r'^[^\w`]'),
        ),
        LanguageConventions(
            family='csharp', test_annotation_markers=_CSHARP_TEST_MARKERS,
            entry_point_files=frozenset({'program.cs', 'startup.cs'}),
            # ASP.NET Core resolves middleware Invoke/InvokeAsync and Startup's
            # Configure/ConfigureServices by name, through reflection.
            implicit_names=frozenset({'Main', 'Invoke', 'InvokeAsync', 'Configure', 'ConfigureServices'}),
            entry_point_decorators=CSHARP_ENTRY_POINT_DECORATORS,
            stdlib_key=_prefix_stdlib_key('System'),
        ),
        LanguageConventions(
            family='java', test_annotation_markers=_JVM_TEST_MARKERS,
            entry_point_files=frozenset({'main.java', 'app.java', 'application.java'}),
            implicit_names=frozenset({'main'}),
            entry_point_decorators=JVM_ENTRY_POINT_DECORATORS,
            stdlib_key=_prefix_stdlib_key('java', 'javax', 'jdk'),
            test_name_prefixes=('test',), test_prefixes_in_test_files_only=True,
            test_file_patterns=(re.compile(r'^(.+?)Tests?\.java$'), re.compile(r'^Test(.+)\.java$')),
            test_symbol_patterns=(re.compile(r'(?:void|fun)\s+`?test(\w+)', re.MULTILINE),),
        ),
        LanguageConventions(
            family='kotlin', test_annotation_markers=_JVM_TEST_MARKERS,
            entry_point_files=frozenset({'main.kt', 'application.kt'}),
            implicit_names=frozenset({'main'}),
            entry_point_decorators=JVM_ENTRY_POINT_DECORATORS,
            stdlib_key=_prefix_stdlib_key('kotlin', 'java', 'javax'),
            test_name_prefixes=('test',), test_prefixes_in_test_files_only=True,
            test_file_patterns=(re.compile(r'^(.+?)Tests?\.kts?$'), re.compile(r'^Test(.+)\.kts?$')),
            test_symbol_patterns=(re.compile(r'(?:void|fun)\s+`?test(\w+)', re.MULTILINE),),
        ),
        LanguageConventions(
            family='scala', test_annotation_markers=_JVM_TEST_MARKERS,
            stdlib_key=_prefix_stdlib_key('scala', 'java', 'javax'),
        ),
    )
}

_ALL_BUILTIN_NAMES: FrozenSet[str] = frozenset().union(*(c.builtins for c in _CONVENTIONS.values()))


def conventions_for(family: str) -> LanguageConventions:
    """Conventions for a language family slug; the EMPTY profile if none registered."""
    return _CONVENTIONS.get(family, EMPTY)


def family_for_path(file_path: str) -> str:
    """Coarse language family for a file path, or '' if unknown."""
    lang = language_for_extension(Path(file_path).suffix.lower())
    return FAMILY_BY_LANGUAGE.get(lang, '') if lang else ''


def conventions_for_path(file_path: str) -> LanguageConventions:
    """Conventions for the language of *file_path*."""
    return conventions_for(family_for_path(file_path))


def is_builtin_anywhere(name: str) -> bool:
    """True if *name* is a builtin in at least one registered family (cheap pre-filter)."""
    return name in _ALL_BUILTIN_NAMES
