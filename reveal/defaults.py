"""Central configuration defaults for Reveal.

All magic numbers and thresholds should be defined here.
These can be overridden by config files and environment variables.

Usage:
    from reveal.defaults import RuleDefaults

    threshold = self.get_threshold('threshold', RuleDefaults.CYCLOMATIC_COMPLEXITY)
"""

import re
from typing import Dict


# Canonical set of directories that directory walks skip by default.
#
# Single source of truth: previously this set was redefined (with drifting
# contents) in 9+ modules — ast/stats/surface/grep/pack/file_checker/patches —
# so one walker would skip `.ruff_cache`/`htmlcov` while another descended into
# it. This is the superset; every caller either tests membership directly or
# combines it with a `startswith('.')` guard, both of which a superset satisfies.
# Symbols that dominate `calls://?rank=callers` on TypeScript codebases but carry
# no architectural signal — test-framework lifecycle hooks, assertion helpers, and
# mock APIs.  Suppressed by default in rank_by_callers; opt back in via
# ?test-framework=true.
TEST_FRAMEWORK_CALLEE_NAMES = frozenset({
    # Test structure hooks (Jest / Vitest / Jasmine / Cypress)
    'describe', 'it', 'test',
    'beforeEach', 'afterEach', 'beforeAll', 'afterAll',
    'fdescribe', 'fit', 'xdescribe', 'xit', 'xtest',
    # Assertion entry point and mock APIs
    'expect', 'mock', 'spyOn', 'vi', 'jest', 'cy',
    # Jest / Vitest matchers (chained on expect() — appear as standalone callees)
    'toBe', 'toEqual', 'toStrictEqual', 'toBeNull', 'toBeUndefined',
    'toBeDefined', 'toBeTruthy', 'toBeFalsy', 'toBeNaN', 'toBeCloseTo',
    'toContain', 'toContainEqual', 'toHaveLength', 'toHaveProperty',
    'toHaveBeenCalled', 'toHaveBeenCalledWith', 'toHaveBeenCalledTimes',
    'toHaveBeenLastCalledWith', 'toHaveBeenNthCalledWith',
    'toHaveReturnedWith', 'toHaveReturnedTimes',
    'toThrow', 'toThrowError', 'toMatchSnapshot', 'toMatchInlineSnapshot',
    'toMatchObject', 'resolves', 'rejects', 'not',
})

SKIP_DIRECTORIES = frozenset({
    # Version control
    '.git',
    # Python caches / build
    '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',
    '.cache', '.hypothesis',
    # Virtual environments (dotted form only — bare `venv`/`env` are ambiguous,
    # see AMBIGUOUS_SKIP_DIRECTORIES)
    '.venv', '.env',
    # Installed packages
    'node_modules', 'site-packages', 'dist-packages',
    # Test/CI runners
    '.tox', '.nox', 'htmlcov',
    # Build / packaging artifacts
    '.eggs', 'sdist',
    # Benchmark / eval tooling
    '.benchmarks', '.deepeval',
})

# BACK-552: `env`/`venv`/`build`/`dist` are conventional virtualenv/build-output
# names, but they are not *reserved* — a real source package can legitimately
# be named any of them (confirmed on Elasticsearch: `org.elasticsearch.env`,
# 297 files, was silently excluded from every directory walk by bare-name
# match alone). Unlike SKIP_DIRECTORIES, membership here is not sufficient to
# skip a directory — callers must also check
# ``reveal.utils.path_utils.is_skippable_dir()``, which only skips these names
# when the directory itself carries no direct evidence of being real source
# (no source-code files at its own top level).
AMBIGUOUS_SKIP_DIRECTORIES = frozenset({'env', 'venv', 'build', 'dist'})

# Canonical test-directory vocabulary (BACK-1199).
#
# Single source of truth: previously three call sites each redefined this
# with drifting contents — surface.py and hotspots.py knew about `spec`,
# but rules/maintainability/M102.py did not, so on any Ruby/RSpec codebase
# (spec/ instead of tests/) M102 treated every spec file as regular source
# and flagged it as "orphaned" (not imported anywhere) when in fact it was
# never expected to be imported at all.
#
# TEST_DIR_NAMES is exact-match — the canonical set every consumer agrees
# on. TEST_DIR_PREFIX is a *broader*, opt-in generalization (also matches
# `testing/`, `test-fixtures/`, etc.) — surface.py's `--source-only` alone
# layers it on top; a bare prefix match is too loose for M102/hotspots,
# which walk real package directories and would false-positive on names
# like `testpkg` (BACK-1199 regression caught during consolidation).
TEST_DIR_PREFIX = 'test'
TEST_DIR_NAMES = frozenset({'test', 'tests', '__tests__', 'spec', 'specs'})

# Vendored/third-party dependency directory names (BACK-1195). Live evidence:
# on a real Ruby/Rails corpus, `overview://`'s top-5 components-by-cohesion
# and top complexity findings were 100% vendored/generated/test code (e.g.
# `vendor/holidays/lib/generated_definitions/`) — the one genuine first-party
# finding ranked below the noise. Exact-match against a single path
# component, same shape as TEST_DIR_NAMES/is_test_dir(); a caller checks
# membership against every component of a file's relative path, not just the
# top-level directory, since vendored trees are often nested (e.g.
# `app/assets/vendor/`).
VENDOR_DIR_NAMES = frozenset({
    'vendor', 'third_party', 'thirdparty', 'node_modules', 'bower_components',
    # BACK-1242: extend beyond the original 5 -- free, no false-positive risk
    # (a directory literally named one of these is essentially always a
    # vendored-dependency convention, same category as 'vendor'/'node_modules').
    'extern', 'externs', '3rdparty', '3rd-party', 'deps',
})

# Filename suffixes marking a minified/bundled build artifact (BACK-1195,
# wishlist-3 addendum B3-4). A small reveal-specific list, deliberately not a
# port of GitHub Linguist's ruleset — measured at only 6.5% coverage of the
# non-first-party files on the reporter's reference corpus, and Linguist has
# no test-directory category at all (misses `spec/`, this ticket's single
# largest distortion class). Kept for any caller doing a literal suffix test.
MINIFIED_FILE_SUFFIXES = (
    '.min.js', '.min.css', '-min.js', '-min.css', '.bundle.js',
)

# BACK-1258: the plain endswith() test above was case-sensitive and blind to
# both ESM/CJS extensions and content-hashed build output, so `app.min.1a2b3c.js`
# (webpack/vite/sprockets' default naming), `bundle.min.mjs` and `A.MIN.JS` all
# classified as first_party — which is how a vendored bundle reached #1 in a
# hotspots ranking tagged `null`. Marker and extension are matched with an
# optional digest between them.
MINIFIED_FILENAME_RE = re.compile(
    r'[.\-](min|bundle)([.\-][0-9a-zA-Z]{6,})?\.(js|mjs|cjs|css)$',
    re.IGNORECASE,
)


class RuleDefaults:
    """Default thresholds for quality rules.

    Organized by rule category. Each constant documents the rule(s) that use it.
    """

    # Complexity Rules
    CYCLOMATIC_COMPLEXITY = 10           # C901: Cyclomatic complexity threshold
    NESTING_DEPTH_MAX = 4                # C905: Maximum nesting depth
    FUNCTION_LENGTH_WARN = 75            # C902: Function length warning
    FUNCTION_LENGTH_ERROR = 100          # C902: Function length error (god function)

    # File Quality Rules
    FILE_LENGTH_WARN = 500               # M101: File length warning
    FILE_LENGTH_ERROR = 1000             # M101: File length error (too large)
    MAX_LINE_LENGTH = 100                # E501: Maximum line length

    # Code Smell Rules
    MAX_FUNCTION_ARGUMENTS = 5           # R913: Maximum function arguments
    MAX_PROPERTY_LINES = 8               # B003: Maximum property/getter lines

    # Duplication Rules
    MIN_FUNCTION_SIZE = 8                # D002: Minimum function size for comparison
    MIN_SIMILARITY = 0.50                # D002: Minimum similarity score
    MAX_DUPLICATE_CANDIDATES = 5         # D002: Maximum candidates to report

    # Maintainability Rules
    MIN_LIST_SIZE = 5                    # M104: Minimum list size for detection
    MIN_DICT_VALUE_SIZE = 3              # M104: Minimum dict value size

    # Link Rules
    LINK_TIMEOUT = 5                     # L002: HTTP request timeout (seconds)
    MIN_CROSS_REFS = 2                   # L005: Minimum cross-references


class AnalyzerDefaults:
    """Default limits for analyzers."""

    JSONL_PREVIEW_LIMIT = 10             # Lines to preview in JSONL files
    DIRECTORY_MAX_ENTRIES = 50           # Max entries per directory
    RELATED_DOCS_LIMIT = 100             # Max related documents to return


class AdapterDefaults:
    """Default limits for adapters."""

    STATS_MAX_FILES = 1000               # Maximum files for stats analysis
    CLAUDE_SESSION_SCAN_LIMIT = 50       # Sessions to scan for claude://
    GIT_COMMIT_HISTORY_LIMIT = 20        # Default commit history depth
    SSL_EXPIRY_WARNING_DAYS = 30         # SSL certificate expiry warning
    SSL_EXPIRY_CRITICAL_DAYS = 7         # SSL certificate expiry critical


class DisplayDefaults:
    """Default limits for display/output."""

    TREE_DIR_LIMIT = 50                  # --dir-limit default
    TREE_MAX_ENTRIES = 200               # --max-entries default
    SNIPPET_CONTEXT_LINES = 3            # Lines of context around matches


# Cross-file call-graph EXTRACTION confidence, per language (BACK-1198).
#
# Grounded in reveal's own measured recall figures (VALIDATION.md, "Cross-File
# Call-Graph Recall") -- NOT invented. Previously calls:// emitted a single
# hardcoded 0.85 confidence regardless of language: identical for a language
# measured at 100% recall (Go, TypeScript, Java, ...) and one with real,
# documented residual gaps (C++ 95.73%, Dart 97.55%). Values below are the
# best POST-FIX recall figure recorded for each language's real-corpus oracle
# validation (20-per-bucket sample where VALIDATION.md reports one, else the
# single measured figure); update this table if VALIDATION.md's numbers
# change. A language absent from this table has not been oracle-validated at
# all -- CALL_GRAPH_DEFAULT_CONFIDENCE is a floor, not a measurement.
#
# This is EXTRACTION confidence only -- "did calls:// find the real call
# edges that exist in the source" -- not the separate, unmeasured question of
# how much a language's dynamic-dispatch idioms (method_missing, reflection,
# eval, ...) hide real callers from ANY static tool. See
# CALL_GRAPH_DYNAMIC_DISPATCH_VOCAB below for that per-language caveat, and
# adapters/calls/adapter.py's `?uncalled` handling for why that query gets
# its own, more conservative framing (derived-signal vs. extraction).
CALL_GRAPH_EXTRACTION_CONFIDENCE: Dict[str, float] = {
    'python': 0.9996,     # reverse 99.96%, forward 100.00%, transitive 99.98%
    'typescript': 1.00,
    'tsx': 1.00,
    'javascript': 1.00,
    'go': 1.00,
    'rust': 1.00,
    'java': 1.00,
    'ruby': 1.00,
    'php': 1.00,
    'csharp': 1.00,
    'kotlin': 0.9979,     # 20/bucket -- residual: tree-sitter-kotlin grammar gap (BACK-738, open)
    'swift': 0.9979,      # 20/bucket -- residual: 2 tree-sitter-swift grammar gaps (BACK-742, open)
    'cpp': 0.9573,        # 20/bucket -- residual mostly oracle-incompleteness, not calls:// bugs
    'c': 1.00,
    'scala': 1.00,
    'zig': 0.9998,        # 8,403/8,405 (20/bucket) -- residual: one file's parse error
    'lua': 1.00,
    'gdscript': 1.00,
    'dart': 0.9755,       # 20/bucket -- residual: tree-sitter-dart generic-call gap (BACK-768)
}

# Prior blanket confidence value, kept as the floor for any language not yet
# oracle-validated in CALL_GRAPH_EXTRACTION_CONFIDENCE above -- a known-stale
# guess, not a claim of measured accuracy.
CALL_GRAPH_DEFAULT_CONFIDENCE = 0.85

# Per-language caveat for the "dynamic dispatch is not resolved" call-graph
# warning (BACK-1198 item 2). Previously this warning's vocabulary was
# Python's regardless of the language being scanned ("getattr, importlib,
# eval/exec" printed verbatim on a Ruby/Java/Go scan, where none of those
# apply). Not exhaustive per language -- covers the dominant, well-known
# dynamic-dispatch idiom(s) for languages with one; CALL_GRAPH_DEFAULT_
# DISPATCH_VOCAB is the honest fallback for any language not listed.
CALL_GRAPH_DYNAMIC_DISPATCH_VOCAB: Dict[str, str] = {
    'python': 'getattr/setattr, importlib, eval/exec',
    'ruby': 'method_missing, define_method, send/public_send, const_missing',
    'javascript': 'eval, Function(), Reflect, computed member access (obj[key]())',
    'typescript': 'eval, Function(), Reflect, computed member access (obj[key]())',
    'tsx': 'eval, Function(), Reflect, computed member access (obj[key]())',
    'php': 'call_user_func(_array), __call/__callStatic, variable functions ($fn())',
    'java': 'reflection (Method.invoke), dynamic proxies',
    'csharp': 'reflection (MethodInfo.Invoke), dynamic, delegates/events',
    'go': 'the reflect package, function values stored in interfaces',
    'rust': 'dyn Trait objects, function pointers/closures stored in fields',
    'kotlin': 'reflection (KFunction.call), function references',
    'swift': 'NSObject/Objective-C runtime dispatch, @dynamicMemberLookup',
    'scala': 'reflection, structural types, dynamic (scala.Dynamic)',
    'lua': 'metatables (__index/__call), _G table lookups',
}
CALL_GRAPH_DEFAULT_DISPATCH_VOCAB = 'runtime dispatch mechanisms specific to this language'

# Per-language description of what calls://?uncalled actually excludes as
# "implicitly invoked, not statically reachable" (BACK-1197). Previously the
# renderer printed Python's own exclusion vocabulary ("__dunder__ methods and
# @property/@classmethod/@staticmethod") unconditionally on every language,
# reading as a completeness caveat while describing exclusions that don't
# apply -- and worse, Ruby's real equivalent (initialize, invoked by .new,
# never a source-level call edge) was not actually excluded at all: 365 of
# 2,235 uncalled entries (16.3%) on one real corpus. See
# adapters/calls/index.py's _RUBY_IMPLICIT_NAMES for the matching exclusion
# logic -- this dict is the disclosure half, that's the enforcement half.
CALL_GRAPH_IMPLICIT_EXCLUSION_VOCAB: Dict[str, str] = {
    'python': '__dunder__ methods and @property/@classmethod/@staticmethod',
    'ruby': "initialize (invoked by .new), included/extended/inherited/method_missing/"
            "respond_to_missing? (Ruby's module/metaprogramming callback hooks)",
    'javascript': 'constructor methods (invoked by `new`, never a call expression)',
    'typescript': 'constructor methods (invoked by `new`, never a call expression)',
    'tsx': 'constructor methods (invoked by `new`, never a call expression)',
}
CALL_GRAPH_DEFAULT_IMPLICIT_EXCLUSION_VOCAB = (
    "constructors and language-runtime-invoked lifecycle hooks specific to this language"
)


# Environment variable overrides
# Maps env var names to (class_name, attribute_name)
ENV_OVERRIDES = {
    'REVEAL_C901_THRESHOLD': ('RuleDefaults', 'CYCLOMATIC_COMPLEXITY'),
    'REVEAL_C905_MAX_DEPTH': ('RuleDefaults', 'NESTING_DEPTH_MAX'),
    'REVEAL_E501_MAX_LENGTH': ('RuleDefaults', 'MAX_LINE_LENGTH'),
    'REVEAL_M101_WARN': ('RuleDefaults', 'FILE_LENGTH_WARN'),
    'REVEAL_M101_ERROR': ('RuleDefaults', 'FILE_LENGTH_ERROR'),
    'REVEAL_DIR_LIMIT': ('DisplayDefaults', 'TREE_DIR_LIMIT'),
}
