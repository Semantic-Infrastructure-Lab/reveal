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

Fields exist only where an adapter consumes them today. ``stdlib_classifier``
(BACK-1275) and doc-comment style are deliberately not stubbed in yet.
"""

import builtins as _builtins_module
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, Optional, Pattern, Tuple

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
    # Definition names invoked by the language/runtime, never by a call expression.
    implicit_names: FrozenSet[str] = frozenset()
    # Same, by pattern (Python `__dunder__`).
    implicit_name_pattern: Optional[Pattern[str]] = None
    # Decorators that mark a test-runner entry point and are captured as `decorators`.
    test_decorators: FrozenSet[str] = frozenset()
    # Name conventions a test runner collects without an explicit call.
    test_name_prefixes: Tuple[str, ...] = ()
    test_lifecycle_names: FrozenSet[str] = frozenset()
    # Pattern-based test names (Go `TestXxx`), optionally only in files ending in
    # one of `test_file_suffixes` (Go requires `_test.go`; empty = any file).
    test_name_pattern: Optional[Pattern[str]] = None
    test_file_suffixes: Tuple[str, ...] = ()
    # Source-text markers for test attributes/annotations (`[Fact]`, `@Test`).
    # Used where the marker is not (reliably) captured as a decorator.
    test_annotation_markers: Tuple[str, ...] = ()

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
            return True
        if self.test_name_pattern and self.test_name_pattern.match(name):
            return not self.test_file_suffixes or file_path.endswith(self.test_file_suffixes)
        return False


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
            builtins=PYTHON_BUILTINS,
            implicit_decorators=frozenset({'property', 'classmethod', 'staticmethod'}),
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
        LanguageConventions(family='js', implicit_names=frozenset({'constructor'})),
        # BACK-1197: `initialize` is invoked by .new; the rest are Module/Class
        # hook callbacks and metaprogramming dispatch.
        LanguageConventions(family='ruby', implicit_names=frozenset({
            'initialize', 'included', 'extended', 'inherited',
            'method_missing', 'respond_to_missing?',
        })),
        # `main` and `init` are run by the runtime. `go test` collects
        # Test/Benchmark/Example/Fuzz functions in _test.go files; the name after
        # the prefix must not start with a lowercase letter (`Testable` is not a test).
        LanguageConventions(
            family='go',
            implicit_names=frozenset({'main', 'init'}),
            test_name_pattern=re.compile(r'^(Test|Benchmark|Example|Fuzz)(?![a-z])'),
            test_file_suffixes=('_test.go',),
        ),
        # `#[test]`-family attributes are captured as decorators (raw `#[...]` text,
        # reduced to the bare last path segment by the calls adapter).
        LanguageConventions(
            family='rust',
            implicit_names=frozenset({'main'}),
            test_decorators=frozenset({'test', 'bench', 'rstest'}),
        ),
        LanguageConventions(family='csharp', test_annotation_markers=_CSHARP_TEST_MARKERS),
        LanguageConventions(family='java', test_annotation_markers=_JVM_TEST_MARKERS),
        LanguageConventions(family='kotlin', test_annotation_markers=_JVM_TEST_MARKERS),
        LanguageConventions(family='scala', test_annotation_markers=_JVM_TEST_MARKERS),
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
