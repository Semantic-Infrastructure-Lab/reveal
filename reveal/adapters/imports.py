"""imports:// adapter - Import graph analysis.

Analyze import relationships in codebases:
- List all imports in a directory
- Detect unused imports (?unused)
- Find circular dependencies (?circular)
- Validate layer violations (?violations)

Usage:
    reveal imports://src                     # All imports
    reveal 'imports://src?unused'            # Find unused
    reveal 'imports://src?circular'          # Find cycles
"""

import difflib
import os
import sys
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional, Sequence, Tuple, cast
from reveal.reveal_types import CONTRACT_VERSION, PathFailure, WarningEntry

from .base import ResourceAdapter, register_adapter, register_renderer
from .help_data import load_help_data
from ..core import disk_cache
from ..utils.formatting import cwd_path
from ..utils import print_json_result
from ..analyzers.imports import ImportGraph, ImportStatement
from ..analyzers.imports.types import (
    LAZY_EXCLUDE, LAZY_INCLUDE, LAZY_MODES, ImportAnalysis, ImportExtraction,
)
from ..analyzers.imports.classify import classify_import, local_package_names, package_table
from ..analyzers.imports.unused import describe_unused
from ..conventions import conventions_for_path, family_for_path, same_package_families
from ..analyzers.imports.base import build_project_namespaces
from ..analyzers.imports.layers import load_layer_config
from ..utils.query import parse_query_params
from ..utils.query_parser import CliBinding, ParamSpec, QueryParams, ResourceSpec
from ..utils.query_binding import boolean_value
from ..analyzers.imports.views import (
    ImportView, _unused_not_checked, detect_autoload_regime, _component_cohesion,
    _cohesion_fields, _cohesion_declined, COHESION_DECLINED_RULE, COHESION_DECLINED_REASON,
)
from ..analyzers.imports import diagnostics as import_diagnostics
from ..analyzers.imports.diagnostics import worker_lost_warning, parse_failure_warning, file_loss_warnings
from ..analyzers.imports import service as import_analysis
from ..analyzers.imports.build_cache import (
    _ADAPTER_IMPORT_GRAPH_NAMESPACE, _candidate_set_fingerprint, _graph_cache_key, _GRAPH_MEMO,
)
from ..analyzers.imports.extraction import (
    extract_one_file as _extract_one_file, lost_extraction as _lost_extraction,
)
from ..analyzers.imports import resolution
from ..registry import get_code_extensions
from ..utils.path_utils import TestLayout, hidden_entries_warning, to_posix, to_relative_display
from ..utils.query_control import ScanBudget
from ..utils.results import ResultBuilder, note_truncation
from ..utils.warning_render import meta_warning_lines

def _discovery_incomplete(result: Dict[str, Any]) -> bool:
    """Whether the available import graph lost required directory enumeration."""
    return any(w.get('type') == 'analysis_incomplete' for w in result.get('meta', {}).get('warnings', []))


def _module_label(path: str) -> str:
    p = Path(path)
    return '/'.join(p.parts[-2:]) if p.name == '__init__.py' else p.name


def unused_not_checked_line(not_checked: Dict[str, int]) -> str:
    """'Unused imports not checked for X' disclosure (empty if none) -- BACK-1398."""
    if not not_checked:
        return ''
    exts = ', '.join(f'{ext} ({n} file{"s" if n != 1 else ""})' for ext, n in not_checked.items())
    return f"⚠ Unused imports not checked — no unused-import detection for: {exts}"


def coverage_warning_line(unsupported: Dict[str, int]) -> str:
    """One-line 'N files skipped, no import support for X' warning (empty if none).

    Shared by imports:// and every downstream command (architecture, overview)
    that builds an ImportGraph and needs to disclose the same gap (BACK-518
    part 2) instead of silently presenting a partial graph as the whole tree.
    """
    if not unsupported:
        return ''
    skipped_total = sum(unsupported.values())
    exts = ', '.join(f"{ext} ({n})" for ext, n in sorted(unsupported.items()))
    return f"⚠ {skipped_total} code file(s) not analyzed — no import support for: {exts}"


# BACK-1245: cheap, conservative, manifest-only detection of a convention-
# autoloading framework regime. Rails/Django/Laravel load most application
# code by naming convention, not require/import/use -- for these, the
# explicit import graph these adapters build is structurally thin (near-
# meaningless, not just "somewhat approximate"), but the only prior
# disclosure was a generic one-liner ("dynamically loaded files may appear
# as entry points") that reads as a minor edge case regardless of which
# regime is in play. False negatives here (a framework not in this table)
# are safe -- callers just keep seeing the generic caveat; a false positive
# would not be, so detection intentionally requires an unambiguous manifest
# marker, not a guess from file extensions alone.

def autoload_regime_warning(regime: Optional[Dict[str, str]]) -> str:
    """Strong, framework-named disclosure line for when detect_autoload_regime()
    finds a hit -- distinct from the generic 'dynamically loaded files may
    appear as entry points' caveat this is meant to sit alongside, not
    replace (BACK-1245: that caveat reads as a minor edge case even on a
    codebase where it describes almost the entire application).
    """
    if not regime:
        return ''
    return (
        f"⚠ {regime['framework']} detected ({regime['evidence']}) — this framework "
        "loads most application code by naming convention, not require/import. "
        "fan-in/fan-out/circular/entry-point signals below reflect only the small "
        "explicit import graph, not real usage; treat them as unreliable for this "
        "codebase, not merely approximate."
    )


def _lazy_value(value: Any) -> str:
    if not isinstance(value, str):  # a bare `&lazy` parses as True
        raise TypeError(value)
    return value


# BACK-2077: which edges an edge-derived answer counts, by the scope of the imports behind
# each edge. No default here: every view has its own (cycles leave lazy edges out).
_LAZY = ParamSpec(
    'lazy', 'string',
    'Function-level (lazy) import edges: include them, exclude them (load-time edges only: '
    'the architecture view) or show only them. Default: ?circular and has_cycles exclude, '
    'every other view includes. Python, JavaScript, TypeScript and TSX record import scope; '
    'other languages\' edges count as load-time under every value, and the printed rule names them',
    None, _lazy_value,
    examples=('imports://src?rank=fan-in&lazy=exclude', 'imports://src?circular&lazy=include'),
    choices=LAZY_MODES,
)

def _choice_value(value: Any) -> str:
    if not isinstance(value, str):  # a bare `&scope` parses as True
        raise TypeError(value)
    return value


def _max_files_value(value: Any) -> int:
    if isinstance(value, bool):
        raise TypeError(value)
    return int(value)


def _importers_value(value: Any) -> Any:
    """A bare ``?importers`` (True) asks for every module under the path; a value names one file."""
    if value is True:
        return True
    if not isinstance(value, str) or not value:
        raise TypeError(value)
    return value


# BACK-1054 (slice S2 of folding depends://, deps:// and calls?modules into imports://): where an
# answer is resolved, which rows it shows and which importers count. Each is read where it is
# applied; none of them enters a cache key (the root does).
SCOPE_ROOT, SCOPE_PATH = 'root', 'path'
_SCOPE = ParamSpec(
    'scope', 'string',
    'root (default): resolve at the project root the climb finds (?root=, .reveal.yaml root: true, '
    'package marker, VCS root, else the requested directory) and show rows under the requested path, '
    'counting importers from anywhere under the root. path: the requested path is the scan root, '
    'as imports:// resolved before (architecture, overview, pack and diff pass it)',
    SCOPE_ROOT, _choice_value,
    examples=('imports://src?rank=fan-in&scope=path',), choices=(SCOPE_ROOT, SCOPE_PATH),
)
_TESTS = ParamSpec(
    'tests', 'string',
    'Importers under a project-relative test path (tests/ or test/ directories, '
    'test_*.py, *_test.go, *.spec.ts, ...): include them (default) or exclude them from every count. '
    'Checkout ancestors and the selected project name are ignored; a disclosed markerless '
    'scan-root fallback retains its own directory name',
    'include', _choice_value,
    examples=('imports://src?rank=fan-in&tests=exclude',), choices=('include', 'exclude'),
)
_ROOT = ParamSpec(
    'root', 'string',
    'Pin the scan root to DIR (beats .reveal.yaml, package and VCS markers): resolved against cwd, '
    'must be an existing directory containing the path, not a filesystem/home/system root; a refused '
    'value says why and the climb decides. Ignored with scope=path',
    None, _choice_value, examples=('imports://src/app.py?importers&root=.',),
)
_MAX_FILES = ParamSpec(
    'max_files', 'integer',
    'Source files the walk may keep (default 20000); a capped walk is disclosed in metadata.scan_budget '
    'and as a warning, never silently partial',
    import_analysis.DEFAULT_FILE_CAP, _max_files_value, examples=('imports://.?importers&max_files=50000',), minimum=1,
)
_IMPORTERS = ParamSpec(
    'importers', 'string',
    'Who imports what: bare (or on a directory) lists every module under the path with its sorted '
    'importers; =FILE (relative to the path) or a file path lists that file\'s importers with the import '
    'line, scope and the cascade stage (via) of each edge',
    None, _importers_value, names='file',
    examples=('imports://src?importers', 'imports://src?importers=utils.py', 'imports://src/utils.py?importers'),
)
_REQUEST_SPECS = (_LAZY, _SCOPE, _TESTS, _ROOT, _MAX_FILES, _IMPORTERS)

# Component cohesion (internal / (internal + outgoing) imports) is declined, not computed, for a component whose
# files are mostly in a language where one package/module sees its own files with no import (BACK-1428).


# BACK-2194: the Graphviz module view, the replacement for calls ?modules &format=dot. URI-only, as
# on calls:// (dot has no --format spelling); it draws the edges ?importers lists for a directory.
_FORMAT = ParamSpec(
    'format', 'string',
    'URI output override for ?importers on a directory: dot draws one importer -> module edge per '
    'listed importer as Graphviz (pipe to dot -Tsvg); text and json follow --format',
    None, _choice_value, examples=('imports://src?importers&scope=path&format=dot',),
    choices=('text', 'json', 'dot'), role='presentation',
)


def _flag(name: str, description: str) -> ParamSpec:
    return ParamSpec(name, 'boolean', description, False, boolean_value, (f'imports://src?{name}',),
                     role='operation', cli=CliBinding((f'--{name}',), action='store_true'))


def _top_value(value: Any) -> int:
    if isinstance(value, bool):
        raise TypeError(value)
    return int(value)


# The answer types --verbose expands (the renderers that take it).
_VERBOSE_VIEWS = frozenset({'unused_imports', 'circular_dependencies', 'layer_violations',
                           'module_importers', 'importer_summary', 'external_packages'})


# The declaration the `reveal imports` subcommand and the declared URI route bind (BACK-1054, D6):
# every parameter imports:// reads. The views read presence for the flags, as the URI always did.
PARAM_SPECS: Tuple[ParamSpec, ...] = (
    _flag('unused', 'Find unused imports'),
    _flag('circular', 'Detect circular dependencies (load-time edges unless &lazy says otherwise)'),
    _flag('violations', 'Check layer violations (requires .reveal.yaml layers)'),
    ParamSpec('rank', 'string', 'Rank files by fan-in (one value: fan-in)', None, _choice_value,
              ('imports://src?rank=fan-in',), choices=('fan-in',), role='operation',
              cli=CliBinding(('--rank',), metavar='fan-in')),
    ParamSpec('top', 'integer', 'Limit ?rank rows (default: all)', None, _top_value,
              ('imports://src?rank=fan-in&top=20',), minimum=0, role='analysis',  # the adapter cuts the rows
              cli=CliBinding(('--top',), metavar='N')),
    _flag('entrypoints', 'Files with fan-in 0 (entry points, scripts or dead code)'),
    _flag('components', 'Score each directory as a component'),
    _flag('external', 'Package table: unresolved (third-party or unresolved-local) and stdlib packages by use'),
    ParamSpec('verbose', 'boolean', 'Show everything instead of a summary (same as --verbose)', False,
              boolean_value, ('imports://src?circular&verbose',), role='presentation'),
    *(ParamSpec(spec.name, spec.type, spec.description, spec.default, spec.convert, spec.examples,
                minimum=spec.minimum, choices=spec.choices, role='analysis',
                cli=CliBinding((f'--{spec.name.replace("_", "-")}',), dest=spec.name,
                               metavar=spec.name.upper()))
      for spec in _REQUEST_SPECS if spec is not _IMPORTERS),
    ParamSpec(_IMPORTERS.name, _IMPORTERS.type, _IMPORTERS.description, None, _IMPORTERS.convert,
              _IMPORTERS.examples, role='operation', names=_IMPORTERS.names,
              cli=CliBinding(('--importers',), nargs='?', metavar='FILE')),
    _FORMAT,
)
_FLAG_NAMES = frozenset(spec.name for spec in PARAM_SPECS if spec.type == 'boolean')

_SCHEMA_QUERY_PARAMS = {
    'unused': {
        'type': 'flag',
        'description': 'Find unused imports in codebase',
        'examples': ['imports://src?unused']
    },
    'circular': {
        'type': 'flag',
        'description': 'Detect circular dependencies',
        'examples': ['imports://src?circular']
    },
    'violations': {
        'type': 'flag',
        'description': 'Check for layer violations (requires config)',
        'examples': ['imports://src?violations']
    },
    'rank': {
        'type': 'enum',
        'values': ['fan-in'],
        'description': 'Rank files by structural metric. fan-in: count of files that import each file (higher = more central; 0 = entry point or dead code)',
        'examples': ['imports://src?rank=fan-in', 'imports://src?rank=fan-in&top=20']
    },
    'top': {
        'type': 'integer',
        'description': 'Limit results for ?rank (default: all files)',
        'examples': ['imports://src?rank=fan-in&top=20']
    },
    'entrypoints': {
        'type': 'flag',
        'description': 'List files with fan-in=0 — nothing imports them (entry points, scripts, or dead code); sorted by fan-out descending',
        'examples': ['imports://src?entrypoints']
    },
    'components': {
        'type': 'flag',
        'description': 'Score each directory as a component: cohesion (internal/outgoing imports; null/n/a for a component mostly in Go, Java, Kotlin, C#, Scala or Swift, with cohesion_rule saying why), coupling (incoming), top bridge file',
        'examples': ['imports://src?components']
    },
    'external': {
        'type': 'flag',
        'description': ('Package table (the deps:// dashboard\'s, as JSON): every import of the files under the path '
                        'classified on resolution truth first -- resolved in the tree (internal), stdlib (a '
                        'language rule or marker, never Python\'s list for another language) or unresolved '
                        '(third-party or an unresolved local) -- with uses per package, the languages importing '
                        'each unresolved package, and import statements per file. &tests=exclude drops test files'),
        'examples': ['imports://src?external', 'imports://src?external&scope=path'],
    },
    'verbose': {
        'type': 'flag',
        'description': 'Show everything instead of a summary: every file in a cycle group plus its cycle edges, all unused imports, all violations, every package. Same as the CLI --verbose',
        'examples': ['imports://src?circular&verbose']
    },
    'lazy': _LAZY.schema(),
    'importers': _IMPORTERS.schema(),
    'scope': _SCOPE.schema(),
    'tests': _TESTS.schema(),
    'root': _ROOT.schema(),
    'max_files': _MAX_FILES.schema(),
    'format': _FORMAT.schema(),
}

# BACK-2077: the counting rule every edge-derived answer carries (service.edge_rule).
_EDGE_RULE_SCHEMA = {
    'type': 'object',
    'properties': {
        'lazy': {'type': 'string', 'enum': list(LAZY_MODES)},
        'lazy_default': {'type': 'boolean'},
        'type_checking': {'type': 'string', 'const': 'excluded'},
        'tests': {'type': 'string', 'enum': ['included', 'importers_not_counted']},
        'scope': {'type': 'string', 'enum': ['scanned_path', 'scan_root']},
        'unclassified_edges': {'type': 'integer'},
        'unclassified_languages': {'type': 'array', 'items': {'type': 'string'}},
        # BACK-1054: where the answer was resolved and which rows it shows.
        'root': {'type': 'string', 'description': 'scan root, relative to the requested path'},
        'root_source': {'type': 'string', 'enum': list(resolution.ROOT_SOURCES)},
        'scope_param': {'type': 'string', 'enum': [SCOPE_ROOT, SCOPE_PATH]},
        'tests_param': {'type': 'string', 'enum': ['include', 'exclude']},
        'via': {'type': 'object', 'description': 'counted edges by the cascade stage that found them',
                'additionalProperties': {'type': 'integer'}},
        'ungated_languages': {'type': 'array', 'items': {'type': 'string'}},
        'ungated_edges': {'type': 'integer'},
        'outside_root_edges': {'type': 'integer', 'description': 'edges whose target lies outside the scan root, not counted'},
        'text': {'type': 'string'},
    },
}

_SCHEMA_OUTPUT_TYPES = [
    {
        'type': 'imports',
        'description': 'Full import listing for all files in the codebase (default output)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'imports'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'files': {'type': 'object'},
                'metadata': {
                    'type': 'object',
                    'properties': {
                        'total_files': {'type': 'integer'},
                        'total_imports': {'type': 'integer'},
                        'has_cycles': {'type': 'boolean'},
                        'cycles_lazy': {'type': 'string', 'enum': list(LAZY_MODES)},
                    }
                },
                'edge_rule': _EDGE_RULE_SCHEMA,
            }
        }
    },
    {
        'type': 'unused_imports',
        'description': 'List of unused imports with file locations',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'unused_imports'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'count': {'type': 'integer'},
                'unused': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'line': {'type': 'integer'},
                            'module': {'type': 'string'}
                        }
                    }
                }
            }
        }
    },
    {
        'type': 'circular_dependencies',
        'description': 'Detected circular import cycles',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'circular_dependencies'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'count': {'type': 'integer'},
                'edge_rule': _EDGE_RULE_SCHEMA,
                'cycles': {
                    'type': 'array',
                    'items': {
                        'type': 'array',
                        'items': {'type': 'string'}
                    }
                }
            }
        }
    },
    {
        'type': 'layer_violations',
        'description': 'Architectural layer violations',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'layer_violations'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'count': {'type': 'integer'},
                'edge_rule': _EDGE_RULE_SCHEMA,
                'violations': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'from_file': {'type': 'string'},
                            'to_file': {'type': 'string'},
                            'layer': {'type': 'string'},
                            'reason': {'type': 'string'}
                        }
                    }
                }
            }
        }
    },
    {
        'type': 'fan_in_ranking',
        'description': 'Files ranked by fan-in (importer count) — high fan-in = core abstractions; zero fan-in = entry points or dead code',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'fan_in_ranking'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'total': {'type': 'integer'},
                'edge_rule': _EDGE_RULE_SCHEMA,
                'entries': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'fan_in': {'type': 'integer'},
                            'fan_out': {'type': 'integer'},
                        }
                    }
                }
            }
        }
    },
    {
        'type': 'components',
        'description': 'Per-directory cohesion and coupling scores — validates directory-as-component hypothesis',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'components'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'total': {'type': 'integer'},
                'edge_rule': _EDGE_RULE_SCHEMA,
                'cohesion_rule': {'type': 'string', 'description': 'Present when any component declined its cohesion: why (BACK-1428)'},
                'components': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'component': {'type': 'string'},
                            'files': {'type': 'integer'},
                            'internal': {'type': 'integer'},
                            'outgoing': {'type': 'integer'},
                            'incoming': {'type': 'integer'},
                            'cohesion': {'type': ['number', 'null'], 'description': 'null = declined, see cohesion_reason (more than half the files are in a same-package-visibility language); declined components sort after measured ones'},
                            'cohesion_reason': {'type': 'string', 'description': 'Only on a declined component'},
                            'top_bridge': {'type': ['string', 'null']},
                        }
                    }
                }
            }
        }
    },
    {
        'type': 'entrypoints',
        'description': 'Files with fan-in=0 — nothing imports them (entry points, scripts, or dead code)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'entrypoints'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'total_scanned': {'type': 'integer'},
                'edge_rule': _EDGE_RULE_SCHEMA,
                'entries': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'},
                            'fan_out': {'type': 'integer'},
                        }
                    }
                }
            }
        }
    }
]

_SCHEMA_OUTPUT_TYPES += [
    {
        'type': 'module_importers',
        'description': 'The files that import one file (?importers on a file, or ?importers=FILE)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'module_importers'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'target': {'type': 'string'},
                'count': {'type': 'integer'},
                'edge_rule': _EDGE_RULE_SCHEMA,
                'importers': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'}, 'line': {'type': 'integer'}, 'module': {'type': 'string'},
                            'names': {'type': 'array', 'items': {'type': 'string'}}, 'type': {'type': 'string'},
                            'is_relative': {'type': 'boolean'}, 'alias': {'type': ['string', 'null']},
                            'scope': {'type': ['array', 'null'], 'items': {'type': 'string'}},
                            'via': {'type': ['array', 'null'], 'items': {'type': 'string'}},
                        },
                    },
                },
            },
        },
    },
    {
        'type': 'importer_summary',
        'description': 'Every module under the path with its sorted importers (?importers on a directory)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'importer_summary'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'total': {'type': 'integer'},
                'edge_rule': _EDGE_RULE_SCHEMA,
                'entries': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'file': {'type': 'string'}, 'fan_in': {'type': 'integer'},
                            'importers': {'type': 'array', 'items': {'type': 'string'}},
                        },
                    },
                },
            },
        },
    },
]

_SCHEMA_OUTPUT_TYPES += [
    {
        'type': 'external_packages',
        'description': 'Unresolved and stdlib packages by use (?external; deps:// printed it in text only)',
        'schema': {
            'type': 'object',
            'properties': {
                'contract_version': {'type': 'string'},
                'type': {'type': 'string', 'const': 'external_packages'},
                'source': {'type': 'string'},
                'source_type': {'type': 'string'},
                'total_imports': {'type': 'integer', 'description': 'import statements counted'},
                'total_files': {'type': 'integer', 'description': 'files with at least one import'},
                'internal_imports': {'type': 'integer', 'description': 'relative, resolved in the tree, or a declared project namespace'},
                'external_packages': {
                    'type': 'array', 'description': 'most used first',
                    'items': {'type': 'object', 'properties': {
                        'package': {'type': 'string'}, 'uses': {'type': 'integer'},
                        'languages': {'type': 'array', 'items': {'type': 'string'}}}},
                },
                'stdlib_packages': {
                    'type': 'array',
                    'items': {'type': 'object', 'properties': {
                        'package': {'type': 'string'}, 'uses': {'type': 'integer'}}},
                },
                'top_importers': {
                    'type': 'array', 'description': 'import statements per file, most first',
                    'items': {'type': 'object', 'properties': {
                        'file': {'type': 'string'}, 'imports': {'type': 'integer'}}},
                },
            },
        },
    },
]

_SCHEMA_EXAMPLE_QUERIES = [
    {
        'uri': 'imports://src',
        'description': 'Analyze all imports in src directory',
        'output_type': 'imports'
    },
    {
        'uri': 'imports://src?unused',
        'description': 'Find unused imports',
        'cli_flag': '?unused',
        'output_type': 'unused_imports'
    },
    {
        'uri': 'imports://src?circular',
        'description': 'Detect circular dependencies',
        'cli_flag': '?circular',
        'output_type': 'circular_dependencies'
    },
    {
        'uri': 'imports://src?violations',
        'description': 'Check layer violations (requires .reveal.yaml layers config)',
        'cli_flag': '?violations',
        'output_type': 'layer_violations'
    },
    {
        'uri': 'imports://src/main.py',
        'description': 'Analyze imports for a single file (no cycle detection)',
        'output_type': 'imports'
    },
    {
        'uri': 'imports://src?rank=fan-in',
        'description': 'Rank all files by fan-in — surface core abstractions and entry points',
        'output_type': 'fan_in_ranking'
    },
    {
        'uri': 'imports://src?rank=fan-in&top=20',
        'description': 'Top-20 files by fan-in',
        'output_type': 'fan_in_ranking'
    },
    {
        'uri': 'imports://src?rank=fan-in&lazy=exclude',
        'description': 'Fan-in over load-time (module-level) imports only: the architecture view',
        'output_type': 'fan_in_ranking'
    },
    {
        'uri': 'imports://src?circular&lazy=include',
        'description': 'Cycles counting function-level (lazy) imports too',
        'output_type': 'circular_dependencies'
    },
    {
        'uri': 'imports://src/utils.py?importers',
        'description': 'Who imports utils.py, from anywhere under the project root',
        'output_type': 'module_importers'
    },
    {
        'uri': 'imports://src?importers&tests=exclude',
        'description': 'Every module under src with its importers, test importers not counted',
        'output_type': 'importer_summary'
    },
    {
        'uri': 'imports://src?external',
        'description': 'Unresolved (third-party) and stdlib packages by use',
        'output_type': 'external_packages'
    },
]

_SCHEMA_NOTES = [
    'Supports multiple languages via plugin architecture',
    'Circular dependencies can indicate architectural issues',
    'Layer violations require .reveal.yaml configuration',
    'Unused import detection works with Python, JavaScript, Go, etc.',
    'False positives: imports that trigger side effects (e.g. decorator-based registration) will be flagged as unused — these are intentional and safe to ignore',
    'Fan-in ranking covers static imports only — decorator-based registration and importlib dynamic imports are not captured',
    'Function-level (lazy) imports are edges: ?circular and metadata.has_cycles leave them out by default, every other view counts them; &lazy=include|exclude|only overrides. Each answer states its rule in edge_rule (and a Rule: line in text). Python, JavaScript, TypeScript and TSX record import scope; edge_rule names the languages whose edges it could not classify',
    '?importers=FILE is the single-module reverse lookup and ?external the whole-tree package table (they replace depends:// and deps://, which still answer as retired spellings); use the raw graph for a query neither covers',
    'Scope (BACK-1054): every answer resolves at the project root (&root=, .reveal.yaml root: true, package marker, VCS root, else the requested directory) through the same cascade the retired depends:// used, and shows rows under the requested path; &scope=path makes the requested path the scan root. edge_rule names the root, its source, &scope, &tests, the edges each cascade stage found (via) and the languages no recall oracle gates',
    'Swift module and Ruby Zeitwerk convention edges (via module, convention) are counted as importers but never close a cycle',
]


def _shown_path(path: str, source: Optional[str]) -> str:
    """A row's path as the text views print it. The adapter's answer is already spelled from the
    requested directory (``_path_display``) and is printed as it is: re-spelling it against a FILE
    target turned that file's directory ``.`` into the file's name (BACK-2183). Only an absolute path
    (a result built by hand, BACK-1194) is relativized here."""
    if source and os.path.isabs(path):
        return to_relative_display(path, Path(source))
    return path


class ImportsRenderer:
    """Renderer for import analysis results."""

    @staticmethod
    def _render_edge_rule(result: dict) -> None:
        """The counting rule of an edge-derived answer, as the JSON states it (BACK-2077)."""
        for line in import_analysis.edge_rule_lines(result):
            print(f"  {line}\n")

    @staticmethod
    def _render_unused_imports(result: dict, verbose: bool) -> None:
        """Render unused imports results."""
        count = result['count']
        print(f"\n{'='*60}")
        print(f"Unused Imports: {count}")
        print(f"{'='*60}\n")

        # A language with no import extractor (e.g. Kotlin, Swift, Scala) was
        # never analyzed at all — count == 0 in that case means "not checked,"
        # not "clean." Without this, the text renderer prints the same "✅ No
        # unused imports found!" for both cases, a false-confidence result
        # (BACK-431 feature-breadth pass); the JSON renderer already exposes
        # this via metadata.unsupported_extensions.
        unsupported = result.get('metadata', {}).get('unsupported_extensions') or {}
        if unsupported:
            exts = ', '.join(f'{ext} ({n} file{"s" if n != 1 else ""})' for ext, n in sorted(unsupported.items()))
            print(f"  ⚠ Not analyzed — no import extractor for: {exts}\n")

        not_checked = result.get('metadata', {}).get('unused_not_checked_extensions') or {}
        note = unused_not_checked_line(not_checked)
        if note:
            print(f"  {note}\n")

        # scanned_files (files with a working extractor), not total_files
        # (files with >=1 import statement) — a file can be fully, correctly
        # analyzed and still have zero imports (BACK-431: real WordPress
        # source with no `use`/`require` at all), and total_files would
        # wrongly read as "unchecked" in that case.
        judged_files = result.get('metadata', {}).get('scanned_files', 0) - sum(not_checked.values())
        if count == 0 and judged_files > 0:
            scope = f" in the {judged_files} checked file(s)" if not_checked else ""
            ImportsRenderer._render_no_unused(result, scope)
        elif count == 0:
            pass
        else:
            if verbose:
                for imp in result['unused']:
                    print(f"  {imp['file']}:{imp['line']} - {describe_unused(imp)}")
            else:
                for imp in result['unused'][:10]:
                    print(f"  {imp['file']}:{imp['line']} - {describe_unused(imp)}")
                if count > 10:
                    print(f"\n  ... and {count - 10} more unused imports")
                    print(f"  Run with --verbose to see all {count} unused imports\n")

    @staticmethod
    def _render_no_unused(result: dict, scope: str) -> None:
        """Qualify zero unused observations against required discovery loss."""
        if _discovery_incomplete(result):
            print(f"  No unused imports observed{scope} in the available inputs; analysis is incomplete.\n")
        else:
            print(f"  ✅ No unused imports found{scope}!\n")

    @staticmethod
    def _render_no_cycles(result: dict) -> None:
        """Qualify zero observed cycles against the available resolution population."""
        regime = result.get('metadata', {}).get('autoload_regime')
        total_imports = result.get('metadata', {}).get('total_imports', 0)
        scanned_files = result.get('metadata', {}).get('scanned_files', 0)
        if _discovery_incomplete(result):
            print("  No circular dependencies observed in the available graph; analysis is incomplete.\n")
        elif regime:
            # BACK-1245: an unqualified green check reads as "verified
            # acyclic" when there's barely an explicit import graph to
            # have cycles in -- disclose the denominator instead.
            print(
                f"  ✅ No circular dependencies found among {total_imports} explicit "
                f"import(s) across {scanned_files} file(s).\n"
            )
            print(f"  {autoload_regime_warning(regime)}\n")
        else:
            print("  ✅ No circular dependencies found!\n")

    @staticmethod
    def _render_circular_dependencies(result: dict, verbose: bool) -> None:
        """Render circular dependency groups (one entry per SCC)."""
        count = result['count']
        print(f"\n{'='*60}")
        print(f"Circular Dependencies: {count} cycle group{'s' if count != 1 else ''}")
        print(f"{'='*60}\n")
        ImportsRenderer._render_edge_rule(result)

        if count == 0:
            ImportsRenderer._render_no_cycles(result)
            return

        groups = result['cycles']
        cycle_paths = result.get('cycle_paths', [])
        shown_groups = groups if verbose else groups[:5]
        shown_paths = cycle_paths[:len(shown_groups)] if cycle_paths else []
        for i, group in enumerate(shown_groups, 1):
            n = len(group)
            labels = [_module_label(p) for p in group]
            if verbose or n <= 4:
                label = ', '.join(labels)
            else:
                label = ', '.join(labels[:3]) + f'  [+{n - 3} more files]'
            print(f"  {i}. {n} file{'s' if n != 1 else ''}  {label}")
            if verbose and i - 1 < len(shown_paths):
                path_labels = [_module_label(p) for p in shown_paths[i - 1]]
                print(f"     cycle: {' → '.join(path_labels)}")
        if not verbose and count > 5:
            print(f"\n  ... and {count - 5} more groups")
            print(f"  Run with --verbose to see all {count} groups\n")
        if not verbose and cycle_paths:
            print(f"\n  Tip: add &verbose to see cycle edge sequences (A→B→C→A)")

    @staticmethod
    def _render_layer_violations(result: dict, verbose: bool) -> None:
        """Render layer violation results."""
        count = result['count']
        note = result.get('note', '')
        not_configured = count == 0 and note and 'requires' in note.lower()

        print(f"\n{'='*60}")
        if not_configured:
            print(f"Layer Violations: NOT CONFIGURED")
        else:
            print(f"Layer Violations: {count}")
        print(f"{'='*60}\n")
        ImportsRenderer._render_edge_rule(result)

        if not_configured:
            print(f"  ℹ️  {note}\n")
            print(f"  Add layer rules to .reveal.yaml to enable this check.\n")
        elif count == 0:
            if _discovery_incomplete(result):
                print("  No layer violations observed in the available graph; analysis is incomplete.\n")
            else:
                print(f"  ✅ {note or 'No violations found'}\n")
        else:
            violations = result.get('violations', [])
            shown = violations if verbose else violations[:10]
            for v in shown:
                print(f"  {v['from_file']} -> {v['to_file']}  [{v['layer']}] {v['reason']}")
            if not verbose and count > 10:
                print(f"\n  ... and {count - 10} more violations")
                print(f"  Run with --verbose to see all {count} violations\n")

    @staticmethod
    def _render_cycle_summary(result: dict, display_path: str) -> None:
        """Render observed cycles without declaring completeness after discovery loss."""
        metadata = result.get('metadata', {})
        total_files = metadata.get('total_files', 0)
        total_imports = metadata.get('total_imports', 0)
        has_cycles = metadata.get('has_cycles', False)
        if _discovery_incomplete(result) and not has_cycles:
            print("  Cycles Found:  Unknown (directory discovery incomplete)")
        elif total_files <= 1 and Path(display_path).is_dir():
            print("  Cycles Found:  N/A (only one file scanned — a cycle needs at least two)")
        elif total_files <= 1:
            print("  Cycles Found:  N/A (single-file scan — use imports://dir/ to detect cycles)")
        elif not total_imports:
            print("  Cycles Found:  N/A (no imports found)")
        else:
            print(f"  Cycles Found:  {'❌ Yes' if has_cycles else '✅ No'}")

    @staticmethod
    def _render_import_summary(result: dict, resource: str) -> None:
        """Render import analysis summary."""
        metadata = result.get('metadata', {})
        total_files = metadata.get('total_files', 0)
        total_imports = metadata.get('total_imports', 0)

        display_path = result.get('source', resource)

        print(f"\n{'='*60}")
        print(f"Import Analysis: {display_path}")
        print(f"{'='*60}\n")
        print(f"  Total Files:   {total_files}")
        print(f"  Total Imports: {total_imports}")
        ImportsRenderer._render_cycle_summary(result, display_path)
        print()
        ImportsRenderer._render_edge_rule(result)

        # Honesty note: recognized code files whose language has no import
        # extractor were scanned but contribute nothing — say so instead of
        # letting a low/zero count read as "clean".
        unsupported = metadata.get('unsupported_extensions') or {}
        if unsupported:
            skipped_total = sum(unsupported.values())
            exts = ', '.join(f"{ext} ({n})" for ext, n in unsupported.items())
            print(f"  ⚠️  {skipped_total} code file(s) skipped — no import support for: {exts}")
            print("      (these are not counted above; import graph excludes them)")
            print()

        # Honesty note (BACK-982): a supported file that tree-sitter could not
        # parse silently contributed zero imports/symbols above -- indistinguishable
        # from a genuinely empty file without this. Also means Cycles Found can
        # under-report: a real cycle running through one of these is invisible.
        files_lost_count = metadata.get('files_lost_count', 0)
        lost = set(metadata.get('files_lost', []))
        files_failed_count = metadata.get('files_failed_count', 0) - files_lost_count
        if files_failed_count:
            # Their recovered imports ARE in the graph (BACK-1460); only what sat
            # inside the error region is missing (BACK-1598 wording).
            print(f"  ⚠️  {files_failed_count} file(s) parsed with errors — their imports may be incomplete")
            print("      (import/cycle results can under-report; unused imports not checked in them)")
            parse_failed = [fp for fp in metadata.get('files_failed', []) if fp not in lost]
            for fp in parse_failed[:10]:
                print(f"      - {fp}")
            if files_failed_count > 10:
                print(f"      ... and {files_failed_count - 10} more")
            print()
        # A file lost to a dead pool worker was never parsed (BACK-1753).
        if files_lost_count:
            print(f"  ⚠️  {files_lost_count} file(s) not analyzed — a pool worker died")
            print("      (their imports and structure are missing; results can under-report)")
            for fp in sorted(lost)[:10]:
                print(f"      - {fp}")
            if files_lost_count > 10:
                print(f"      ... and {files_lost_count - 10} more")
            print()
        # The scanned path, not the renderer's `resource` argument, which reaches
        # here as '.' and widened a copy-pasted query to the whole cwd (BACK-1508).
        scope = cwd_path('', str(display_path))
        print("Query options:")
        print(f"  reveal 'imports://{scope}?unused'       - Find unused imports")
        print(f"  reveal 'imports://{scope}?circular'     - Detect circular deps")
        print(f"  reveal 'imports://{scope}?violations'   - Check layer violations")
        print(f"  reveal 'imports://{scope}?rank=fan-in'  - Rank files by fan-in (core abstractions)")
        print()

    @staticmethod
    def _render_fan_in(result: dict, resource: str) -> None:
        """Render rank=fan-in output — files ranked by number of importers."""
        entries = result.get('entries', [])
        total = result.get('total', 0)
        source = result.get('source', resource)

        print(f"\nFan-in ranking: {source}")
        print(f"Files: {len(entries)} of {total}  (fan-in = number of files that import this file)")
        print()
        ImportsRenderer._render_edge_rule(result)

        if not entries:
            print("  No import data found.")
            return

        shown = [_shown_path(e['file'], source) for e in entries]
        col_w = max(min(60, max(len(fpath) for fpath in shown) + 2), 20)

        print(f"  {'FILE':<{col_w}}  {'FAN-IN':>7}  {'FAN-OUT':>8}")
        print(f"  {'-'*col_w}  {'-'*7}  {'-'*8}")
        for e, fpath in zip(entries, shown):
            print(f"  {fpath:<{col_w}}  {e['fan_in']:>7}  {e['fan_out']:>8}")
        print()
        regime = result.get('metadata', {}).get('autoload_regime')
        if regime:
            print(f"  {autoload_regime_warning(regime)}")
        else:
            print("  Note: static imports only — files loaded via dynamic dispatch")
            print("  (importlib, require(), Class.forName, autoload, etc.) show lower fan-in than actual.")
        print()

    @staticmethod
    def _render_file_importers(result: dict, resource: str) -> None:
        rows = result.get('importers', [])
        print(f"\nImporters of {result.get('target', resource)}: {result.get('count', len(rows))}")
        print()
        ImportsRenderer._render_edge_rule(result)
        for row in rows:
            where = f":{row['line']}" if row.get('line') else ''
            tags = ', '.join(filter(None, [', '.join(row.get('via') or []), ', '.join(row.get('scope') or [])]))
            module = f"  {row['module']}" if row.get('module') else ''
            print(f"  {row['file']}{where}{module}" + (f"  [{tags}]" if tags else ''))
        if not rows:
            print('  No importers found.')
        print()

    @staticmethod
    def _render_importers(result: dict, resource: str, verbose: bool) -> None:
        """Render ?importers: one file's importers (module_importers) or every module's (importer_summary)."""
        if result.get('type') == 'module_importers':
            ImportsRenderer._render_file_importers(result, resource)
            return
        entries = result.get('entries', [])
        shown = entries if verbose else entries[:20]
        print(f"\nImporters: {result.get('source', resource)}")
        print(f"Modules with importers: {result.get('total', len(entries))}")
        print()
        ImportsRenderer._render_edge_rule(result)
        for entry in shown:
            print(f"  {entry['file']}  ({entry['fan_in']})")
            for importer in entry['importers'] if verbose else entry['importers'][:5]:
                print(f"      {importer}")
            if not verbose and len(entry['importers']) > 5:
                print(f"      ... and {len(entry['importers']) - 5} more")
        if len(entries) > len(shown):
            print(f"\n  ... and {len(entries) - len(shown)} more modules (--verbose or --format json lists all)")
        if not entries:
            print('  No module under this path has an importer.')
        print()

    @staticmethod
    def _render_dot(result: dict) -> None:
        """?importers&format=dot: one importer -> module edge per listed importer; warnings go to
        stderr so stdout stays valid Graphviz (as every dot view does)."""
        for line in meta_warning_lines(result):
            print(line, file=sys.stderr)

        def quoted(path: str) -> str:
            return '"' + path.replace('\\', '\\\\').replace('"', '\\"') + '"'

        print('digraph modules {')
        print('  rankdir=LR;')
        print('  node [shape=box fontname="monospace"];')
        for entry in result.get('entries', []):
            for importer in entry['importers']:
                print(f'  {quoted(importer)} -> {quoted(entry["file"])};')
        print('}')

    @staticmethod
    def _render_external(result: dict, resource: str, verbose: bool) -> None:
        """Render ?external: the package table, most used first (20 per list unless --verbose)."""
        external, stdlib = result.get('external_packages', []), result.get('stdlib_packages', [])
        scope = result.get('metadata', {}).get('test_scope', {})
        scope_note = f"\n  Test paths: {scope['basis']}; anchor {scope['anchor']}." if scope else ''
        print(f"\nPackages: {result.get('source', resource)}")
        print(f"  {result.get('total_imports', 0)} import(s) in {result.get('total_files', 0)} file(s): "
              f"{result.get('internal_imports', 0)} internal, {len(external)} unresolved package(s), "
              f"{len(stdlib)} stdlib package(s){scope_note}")
        multi_stack = len({lang for entry in external for lang in entry.get('languages', [])}) > 1
        for title, entries in (('Unresolved packages (third-party or unresolved-local)', external),
                               ('Stdlib packages', stdlib)):
            if not entries:
                continue
            shown = entries if verbose else entries[:20]
            print(f"\n{title}: {len(entries)}")
            for entry in shown:
                langs = f"  [{', '.join(entry.get('languages') or []) or '?'}]" if multi_stack and 'languages' in entry else ''
                print(f"  {entry['package']:<30} {entry['uses']:>4} use(s){langs}")
            if len(entries) > len(shown):
                print(f"  ... and {len(entries) - len(shown)} more (--verbose or --format json lists all)")
        if not external and not stdlib:
            print('\n  No unresolved or stdlib imports found.')
        print()

    @staticmethod
    def _render_entrypoints(result: dict, resource: str) -> None:
        """Render ?entrypoints output — files with fan-in=0 (nothing imports them)."""
        entries = result.get('entries', [])
        total_scanned = result.get('total_scanned', 0)
        source = result.get('source', resource)

        print(f"\nEntry points: {source}")
        print(f"Files: {len(entries)} of {total_scanned}  (fan-in=0: nothing imports these — entry points or dead code)")
        print()
        ImportsRenderer._render_edge_rule(result)

        if not entries:
            if _discovery_incomplete(result):
                print("  No entry points observed in the available graph; analysis is incomplete.")
            else:
                print("  No entry points found (every file is imported by at least one other).")
            return

        shown = [_shown_path(e['file'], source) for e in entries]
        col_w = max(min(60, max(len(fpath) for fpath in shown) + 2), 20)

        print(f"  {'FILE':<{col_w}}  {'FAN-OUT':>8}")
        print(f"  {'-'*col_w}  {'-'*8}")
        for e, fpath in zip(entries, shown):
            print(f"  {fpath:<{col_w}}  {e['fan_out']:>8}")
        print()
        regime = result.get('metadata', {}).get('autoload_regime')
        if regime:
            print(f"  {autoload_regime_warning(regime)}")
        else:
            print("  Note: static imports only — files loaded via dynamic dispatch")
            print("  (importlib, require(), Class.forName, autoload, etc.) are false positives here.")
        print()

    @staticmethod
    def _render_components(result: dict, resource: str) -> None:
        """Render ?components output — per-directory cohesion and coupling scores."""
        components = result.get('components', [])
        source = result.get('source', resource)

        print(f"\nComponent analysis: {source}")
        print(f"Components: {len(components)}  (cohesion = internal imports ÷ outgoing imports from component)")
        print()
        ImportsRenderer._render_edge_rule(result)

        if not components:
            print("  No components found.")
            return

        col_w = max(max(len(_shown_path(c['component'], source)) for c in components) + 2, 20)
        col_w = min(col_w, 55)

        print(f"  {'COMPONENT':<{col_w}}  {'FILES':>5}  {'INTERNAL':>8}  {'OUT':>5}  {'IN':>5}  {'COHESION':>9}")
        print(f"  {'-'*col_w}  {'-'*5}  {'-'*8}  {'-'*5}  {'-'*5}  {'-'*9}")

        for c in components:
            name = _shown_path(c['component'], source)
            bridge = c.get('top_bridge')
            bridge_note = f"  ← {Path(bridge).name}" if bridge else ''
            cohesion_pct = 'n/a' if c['cohesion'] is None else f"{c['cohesion'] * 100:.0f}%"
            print(f"  {name:<{col_w}}  {c['files']:>5}  {c['internal']:>8}  {c['outgoing']:>5}  {c['incoming']:>5}  {cohesion_pct:>9}{bridge_note}")

        print()
        print("  Note: low cohesion = files import heavily outside this directory (may not be a real component)")
        if result.get('cohesion_rule'):
            print(f"  Note: {result['cohesion_rule']}")
        print("  Note: static imports only — dynamic dispatch not captured")
        print()

    @staticmethod
    def render_structure(result: dict, format: str = 'text', verbose: bool = False, resource: str = '.') -> None:
        """Render import analysis results.

        Args:
            result: Structure dict from ImportsAdapter.get_structure()
            format: Output format ('text', 'json')
            verbose: Show detailed results
            resource: Resource path for display
        """
        if result.get('_format') == 'dot':
            ImportsRenderer._render_dot(result)
            return
        if format == 'json':
            print_json_result(result)
            return

        for line in meta_warning_lines(result):
            print(line)

        # verbose from query (?verbose) takes precedence over caller arg
        verbose = result.get('verbose', verbose)

        # Text format with progressive disclosure
        if 'type' in result:
            result_type = result['type']
            if result_type == 'unused_imports':
                ImportsRenderer._render_unused_imports(result, verbose)
            elif result_type == 'circular_dependencies':
                ImportsRenderer._render_circular_dependencies(result, verbose)
            elif result_type == 'layer_violations':
                ImportsRenderer._render_layer_violations(result, verbose)
            elif result_type == 'fan_in_ranking':
                ImportsRenderer._render_fan_in(result, resource)
            elif result_type == 'entrypoints':
                ImportsRenderer._render_entrypoints(result, resource)
            elif result_type == 'components':
                ImportsRenderer._render_components(result, resource)
            elif result_type in ('module_importers', 'importer_summary'):
                ImportsRenderer._render_importers(result, resource, verbose)
            elif result_type == 'external_packages':
                ImportsRenderer._render_external(result, resource, verbose)
            else:
                ImportsRenderer._render_import_summary(result, resource)
        else:
            print_json_result(result)

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        """Render file-specific imports.

        Args:
            result: Element dict from ImportsAdapter.get_element()
            format: Output format ('text', 'json')
        """
        if format == 'json':
            print_json_result(result)
            return

        # Text format - file imports
        print(f"Imports for: {result.get('file', 'unknown')}")
        imports = result.get('imports', [])
        if imports:
            for imp in imports:
                print(f"  • {imp['module']} (line {imp['line']})")
        else:
            print("  No imports found")


from ..analyzers.imports.base import get_extractor, get_all_extensions, get_supported_languages  # noqa: E402


# ── BACK-489 P1: parallel per-file extraction ───────────────────────────────
def _path_display(base_path: Path) -> Callable[[Optional[str]], Optional[str]]:
    """Every path an imports answer prints, spelled from the requested directory (a file target's own
    directory): the requested file is named (BACK-1488), a file under the directory is relative to it,
    and any other file is spelled ``../`` from it. That covers a sibling of a file target (BACK-2183), a
    file outside the requested path under scope=root (``../tests/test_x.py``) and a target outside a
    pinned ``&root=`` or a ``&scope=path`` scan root (BACK-2184, BACK-2157), which fell back to the host
    path. Only a path on another Windows drive, which has no relative spelling, is printed as given."""
    base_dir = base_path if base_path.is_dir() else base_path.parent

    def rel(value: Optional[str]) -> Optional[str]:
        if not value:
            return value
        shown = to_relative_display(value, base_dir)
        if not os.path.isabs(shown):
            return to_posix(shown)  # the string: a PurePath's as_posix() keeps a backslash on POSIX
        try:
            return to_posix(os.path.relpath(value, base_dir))
        except ValueError:  # another drive on Windows
            return shown
    return rel


def _spell_metadata_paths(metadata: Dict[str, Any],
                          rel: Callable[[Optional[str]], Optional[str]]) -> Dict[str, Any]:
    """The answer's copy of ``get_metadata()`` with its file lists spelled as the rows are (BACK-2185).

    ``get_metadata()`` keeps absolute ``files_failed``/``files_lost`` for its library readers
    (overview://, the architecture diff), which spell them against their own base; the answer printed
    them as host paths. ``extraction_diagnostics`` keys arrive relative to the target where they can
    be (``rel`` reads such a key from the same directory) and absolute otherwise."""
    for key in ('files_failed', 'files_lost'):
        if isinstance(metadata.get(key), list):
            metadata[key] = [rel(path) or path for path in metadata[key]]
    if isinstance(metadata.get('extraction_diagnostics'), dict):
        metadata['extraction_diagnostics'] = {
            rel(path) or path: causes for path, causes in metadata['extraction_diagnostics'].items()}
    return metadata


def _relativize_importer_paths(result: Dict[str, Any], rel: Callable[[Optional[str]], Optional[str]]) -> None:
    """The importer views (BACK-1054) name every file relative to the requested directory (a file
    target's own directory), as depends:// names them relative to its root."""
    if result.get('target'):
        result['target'] = rel(result['target'])
    for row in result.get('importers', []):
        row['file'] = rel(row['file'])
    for entry in result.get('entries', []):
        entry['file'] = rel(entry['file'])
        entry['importers'] = sorted(cast(str, rel(f)) for f in entry['importers'])


def _relativize_import_dicts(imports: List[Dict[str, Any]], rel: Callable[[Optional[str]], Optional[str]],
                             roots: Tuple[Path, Optional[Path]]) -> None:
    """``file`` and ``resolved`` of formatted import statements, and an absolute ``module`` in the
    project (under the requested path's directory or the scan root, ``roots``): a folded PHP constant
    include keeps its host path as the module, spelled as the ?importers=FILE row does. A module the
    author wrote absolute outside the project is source text, not a host path of ours, and is
    reported as written."""
    base_path, scan_root = roots
    project = (base_path if base_path.is_dir() else base_path.parent, scan_root)
    for imp in imports:
        if imp.get('file'):
            imp['file'] = rel(imp['file'])
        if imp.get('resolved'):
            imp['resolved'] = rel(imp['resolved'])
        module = imp.get('module')
        if module and os.path.isabs(module) and any(
                resolution.path_is_under(Path(module), where) for where in project if where):
            imp['module'] = rel(module)


def _relativize_imports_paths(result: Dict[str, Any], base_path: Path, scan_root: Optional[Path] = None) -> None:
    """Spell the file-path fields of a view's data with ``_path_display`` (the envelope's metadata
    and warnings are spelled in ``_build_response``). The raw structures get_structure() serializes
    to JSON leaked absolute host paths (analyst's filesystem layout/username), same gap as
    overview.py's `_relativize_paths` / deps.py's `_relativize_deps_paths` (BACK-1194 follow-up).
    BACK-1212. Mutates in place; dispatches on result['type'] since get_structure() returns a
    different shape per query param; the text renderers print what this leaves.
    """
    rel = _path_display(base_path)

    def relativize_import_dicts(imports: List[Dict[str, Any]]) -> None:
        _relativize_import_dicts(imports, rel, (base_path, scan_root))

    result_type = result.get('type')
    if result_type == 'imports':
        files = result.get('files')
        if isinstance(files, dict):
            relativized_files = {}
            for file_path, entries in files.items():
                relativize_import_dicts(entries)
                relativized_files[rel(file_path)] = entries
            result['files'] = relativized_files
    elif result_type == 'unused_imports':
        relativize_import_dicts(result.get('unused', []))
    elif result_type in ('fan_in_ranking', 'entrypoints'):
        # Every entry and component carries these keys; rel() leaves an empty value as it is.
        for entry in result.get('entries', []):
            entry['file'] = rel(entry['file'])
    elif result_type == 'components':
        for component in result.get('components', []):
            component['component'] = rel(component['component'])
            component['top_bridge'] = rel(component['top_bridge'])
    elif result_type in ('module_importers', 'importer_summary'):
        _relativize_importer_paths(result, rel)
    elif result_type == 'circular_dependencies':
        for key in ('cycles', 'cycle_paths'):
            groups = result.get(key)
            if groups:
                result[key] = [[rel(fp) for fp in group] for group in groups]
    # 'layer_violations' already relativizes (to_posix + relative_to
    # project_root in _format_violations); 'imports_error' has no file fields.


def _typed_params(params: Any) -> QueryParams:
    """Typed (subcommand) parameters as the URI spells them: an unset flag or option is absent, a
    set flag is present (the views read presence), a bare ``--importers`` (argparse's ``None`` for
    ``nargs='?'``) is ``?importers``."""
    items = list(params.peek_items() if isinstance(params, QueryParams) else dict(params).items())
    if isinstance(params, QueryParams) and not any(v is None or v is False for _k, v in items):
        return params
    typed = QueryParams()
    for key, value in items:
        if value is None and key == _IMPORTERS.name:
            value = True
        if value is None or value is False:
            continue
        typed[key] = True if key in _FLAG_NAMES else value
    return typed


def _named_candidates(name: str, base_dir: Path, root: Path) -> List[Path]:
    """The existing paths ``?importers=NAME`` can mean: relative to the requested directory and
    relative to the scan root (two spellings of one file collapse; two files stay two), or the
    absolute path itself. One owner for the answer and for the result type chosen before it."""
    named = Path(name).expanduser()
    found: List[Path] = []
    for candidate in ([named] if named.is_absolute() else [base_dir / named, root / named]):
        resolved = candidate.resolve()
        if resolved.exists() and resolved not in found:
            found.append(resolved)
    return found


def _scan_root_of(params: Any, target_path: Path) -> resolution.ScanRoot:
    """Where a request resolves: the requested path itself under ``&scope=path``, else the project
    root the shared climb finds (``resolution.choose_scan_root``: ``&root=``, markers, the inferred subtree)."""
    raw_root = params.get(_ROOT.name)  # a read: the build applies it
    if _SCOPE.read(params) == SCOPE_PATH:
        rejected = f'?root={raw_root} is ignored under scope=path' if raw_root else None
        return resolution.ScanRoot(target_path, 'path', override_rejected=rejected)
    return resolution.choose_scan_root(target_path, raw_root)


def _usage_rejection(result: Dict[str, Any]) -> bool:
    """A request the caller got wrong (a target that matches nothing): usage, exit 2."""
    return result.get('usage') is True and 'error' in result


# The views whose rows are findings: `--fail-on findings` exits 1 when the answer has one (BACK-1054
# slice S4: deps' gate over cycles and unused imports, on the imports views it composed).
_FINDINGS_VIEWS = frozenset({'circular_dependencies', 'unused_imports', 'layer_violations'})

# The parameters the build reads (where it resolves, under which file cap): one build, one value.
_BUILD_KEYS = (_SCOPE.name, _ROOT.name, _MAX_FILES.name)


def _validate_params(params: QueryParams) -> None:
    """Validate every supplied value; validation is not application (a preceding query mode may
    take priority, and the view that applies a value reads it)."""
    for key, value in params.peek_items():
        if key == 'rank' and value not in _SCHEMA_QUERY_PARAMS['rank']['values']:
            choices = ', '.join(_SCHEMA_QUERY_PARAMS['rank']['values'])
            raise ValueError(f'rank must be one of: {choices}; got {value!r}')
        if key == _LAZY.name:
            _LAZY.validate(value)
        if key == _FORMAT.name:
            _FORMAT.validate(value)
        for spec in _REQUEST_SPECS[1:] + PARAM_SPECS[3:5]:
            if key == spec.name:
                spec.validate(value)


def _incomplete(result: Dict[str, Any]) -> bool:
    """Whether an imports answer is short of its input: a file parsed with errors or lost to a dead
    worker, a walk the file cap cut short, a directory it could not list (D6: exit 3)."""
    metadata = result.get('metadata') or {}
    if metadata.get('files_failed_count') or metadata.get('files_lost_count'):
        return True
    if (metadata.get('scan_budget') or {}).get('capped'):
        return True
    return any(w.get('type') in ('analysis_incomplete', 'scan_capped')
               for w in (result.get('meta') or {}).get('warnings', []))


@register_adapter('imports')
@register_renderer(ImportsRenderer)
class ImportsAdapter(ResourceAdapter):
    """Analyze import relationships in codebases."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    # --head/--tail/--range cut the module rows of ?importers (and the other ranked views) and say so;
    # a directory ?importers answer is one row per module with ALL its importers, so this is the
    # bound on a corpus with hundreds of thousands of edges (swift), not a per-edge cap (BACK-2192).
    BUDGET_LIST_FIELD = 'entries'
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)
    CLI_QUERY_FLAGS = {'verbose': 'verbose', 'respect_gitignore': 'respect_gitignore=false'}  # `--verbose` == `&verbose` (BACK-1361)

    # D6 (BACK-1054): imports is a declared command, so a usage error exits 2 and an incomplete
    # analysis (a file parsed with errors or lost, a capped walk, a lost directory) exits 3.
    # --fail-on findings exits 1 when a findings view (_FINDINGS_VIEWS) has a row (slice S4).
    RESULT_TYPE = 'imports'
    FINDINGS_POLICIES = ('none', 'findings')
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    PARAM_SPECS = PARAM_SPECS

    def __init__(self, resource: str = '.', query: Optional[str] = None, *,
                 params: Optional[Any] = None, parse_extensions: Optional[frozenset] = None):
        """Initialize imports adapter.

        Args:
            resource: Directory or file path to analyze (e.g., 'src', '/abs/path')
            query: Query string portion (e.g., 'unused', 'circular=true')
            params: the subcommand's typed parameters (a flag left off is not supplied)
            parse_extensions: the extensions the walk keeps and parses, for a caller with its own
                build (depends://, a file target's own family: BACK-525 layer 4, BACK-1054 S6); None
                keeps every extension with an extractor plus recognized code without one (counted
                for the coverage warning, and against the file cap)
        """
        path = resource
        self.analysis = ImportAnalysis()
        # Populated only when _build_graph is called with collect_structures=True
        # (reveal architecture) — per-file AST structures from the shared walk.
        self._structures: List[Dict[str, Any]] = []
        # Handle both absolute and relative paths:
        # - netloc component from URI parsing (imports://relative/path → 'relative/path')
        # - absolute path (imports:///absolute/path → '/absolute/path')
        self._target_path: Optional[Path] = Path(path).resolve() if path else None
        self._query_params = _typed_params(params) if params is not None else parse_query_params(query or '')
        self.query_params = self._query_params  # the name the declared route reads (D6)
        self._warn_unknown_query_params(self._query_params)  # BACK-507
        _validate_params(self._query_params)
        self._local_names_cache: Optional[frozenset] = None  # BACK-1190, lazy
        self._project_namespaces_cache: Optional[set] = None  # BACK-1234, lazy
        # A walk that hid every candidate says so (BACK-2065); set by _build_graph.
        self._scope_hidden: Optional[WarningEntry] = None
        # Where _build_graph resolved and under which file cap (BACK-1054).
        self._scan: Optional[resolution.ScanRoot] = None
        self._test_layout: Optional[TestLayout] = None
        self._scan_budget = ScanBudget(_MAX_FILES.default)
        self._parse_extensions = parse_extensions

    @staticmethod
    def result_type_for(params: Any) -> str:
        """The answer type the query selects, in get_structure's precedence (the path decides
        between the two ?importers types: ``result_type_at``)."""
        supplied = dict(_typed_params(params).peek_items()) if not isinstance(params, str) else {}
        if 'importers' in supplied:
            return 'importer_summary'
        for key, kind in (('unused', 'unused_imports'), ('circular', 'circular_dependencies'),
                          ('violations', 'layer_violations')):
            if key in supplied:
                return kind
        if supplied.get('rank') == 'fan-in':
            return 'fan_in_ranking'
        if 'entrypoints' in supplied:
            return 'entrypoints'
        if 'components' in supplied:
            return 'components'
        if 'external' in supplied:
            return 'external_packages'
        return 'imports'

    @classmethod
    def result_type_at(cls, params: Any, path: str) -> str:
        kind = cls.result_type_for(params)
        if kind != 'importer_summary':
            return kind
        named = dict(_typed_params(params).peek_items()).get('importers')
        target = Path(path).expanduser()
        if isinstance(named, str):
            base = target if target.is_dir() else target.parent
            found = _named_candidates(named, base, _scan_root_of(_typed_params(params), base.resolve()).root)
            target = found[0] if len(found) == 1 else base
        return 'module_importers' if target.is_file() else 'importer_summary'

    @staticmethod
    def public_diagnostic(result: Dict[str, Any]) -> Optional[str]:
        return str(result['error']) if _usage_rejection(result) else None

    @staticmethod
    def execution_facts(result: Any):
        from ..utils.results import AnalysisCompleteness, FailureCause, failure_execution_facts, result_execution_facts
        if not isinstance(result, dict):
            return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
        if _usage_rejection(result):
            return failure_execution_facts(FailureCause.INVALID_REQUEST)
        state = AnalysisCompleteness.INCOMPLETE if _incomplete(result) else AnalysisCompleteness.COMPLETE
        findings = result.get('type') in _FINDINGS_VIEWS and bool(result.get('count'))
        return result_execution_facts(result, completeness=state, findings=findings)

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Analyze imports in directory or file.

        Args:
            **kwargs: Additional parameters (unused, circular, violations flags)

        Returns:
            Dictionary with import analysis results
        """
        target_path = self._target_path or Path('.').resolve()
        query_params = self._query_params
        self._target_path = target_path

        if not target_path.exists():
            return self._build_response('imports_error', error=f"Path not found: {target_path}")

        # Extract imports and build graph
        self._build_graph(target_path)
        return self._present(query_params, kwargs)

    def analyze(self) -> ImportAnalysis:
        """Build the graph this request resolves (its root, file cap and extension family) and return
        it unpresented, for a presenter with its own answer shape over the one engine (depends://,
        BACK-1054 S6). ``scan`` and ``scope_hidden`` describe this build; on a cache hit the
        analysis is shared, so a caller reads it and never changes it."""
        target_path = self._target_path or Path('.').resolve()
        self._target_path = target_path
        self._build_graph(target_path)
        return self.analysis

    @property
    def scan(self) -> Optional[resolution.ScanRoot]:
        """Where the last build resolved (None before one)."""
        return self._scan

    @property
    def scope_hidden(self) -> Optional[WarningEntry]:
        """What the last build's walk hid from the request's focus, judged by this request's walk
        (BACK-2065), never read from a cached build."""
        return self._scope_hidden

    def get_view(self, query: str) -> Dict[str, Any]:
        """Another view of the graph ``get_structure()`` built, without building it again: a
        composer that shows several views side by side reads them from one build (deps:// shows
        the default view, ?circular and ?unused, BACK-1054). ``query`` chooses the view and how it
        counts (``&lazy``, ``&tests``, ``&top``...); a parameter that would change the build
        (``&scope``, ``&root``, ``&max_files``) must equal the built one, else ValueError."""
        params = parse_query_params(query or '')
        self._warn_unknown_query_params(params)
        _validate_params(params)
        changed = [key for key in _BUILD_KEYS
                   if dict(params.peek_items()).get(key) != dict(self._query_params.peek_items()).get(key)]
        if changed:
            raise ValueError(f'get_view cannot change the build ({", ".join(changed)}): construct another adapter')
        target_path = self._target_path or Path('.').resolve()
        if not target_path.exists():
            return self._build_response('imports_error', error=f"Path not found: {target_path}")
        if self.analysis.graph is None:
            raise ValueError('get_view reads the graph get_structure() builds, and none was built')
        self._query_params = self.query_params = params
        return self._present(params, {})

    def _present(self, query_params: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """The answer the query asks for, from the built graph, with paths as the request spelled them."""
        target_path = self._target_path or Path('.').resolve()
        result = self._format_view(query_params, kwargs)
        _relativize_imports_paths(result, target_path, self._scan.root if self._scan else None)
        # Read where the view draws: on any other view the key is unread, and says so.
        if result.get('type') == 'importer_summary' and _FORMAT.read(query_params) == 'dot':
            result['_format'] = 'dot'
        # Read where the view expands: on any other view the flag is unread, and says so.
        if result.get('type') in _VERBOSE_VIEWS and ('verbose' in query_params or kwargs.get('verbose', False)):
            result['verbose'] = True
        return result

    def _format_view(self, query_params: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """The one view the query asks for, in precedence order (?importers first, BACK-1054)."""
        importers = _IMPORTERS.read(query_params)
        if importers is not None:
            result = self._format_importers(importers)
        elif 'unused' in query_params or kwargs.get('unused'):
            result = self._format_unused()
        elif 'circular' in query_params or kwargs.get('circular'):
            result = self._format_circular()
        elif 'violations' in query_params or kwargs.get('violations'):
            result = self._format_violations()
        elif query_params.get('rank') == 'fan-in':
            result = self._format_fan_in()
        elif 'entrypoints' in query_params:
            result = self._format_entrypoints()
        elif 'components' in query_params:
            result = self._format_components()
        elif 'external' in query_params:
            result = self._format_external()
        else:
            result = self._format_all()
        return result

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get imports for a specific file.

        Args:
            element_name: File name (e.g., 'main.py')
            **kwargs: Additional parameters

        Returns:
            Dictionary with imports for that file
        """
        if not self.analysis.graph:
            return None

        # Find matching file
        for file_path, imports in self.analysis.graph.files.items():
            if file_path.name == element_name:
                return {
                    'file': str(file_path),
                    'imports': [self._format_import(stmt) for stmt in imports],
                    'count': len(imports)
                }

        return None

    def integrity_warnings(self, base: Optional[Path] = None, *,
                           spell: Optional[Callable[[Optional[str]], Optional[str]]] = None) -> List[WarningEntry]:
        return import_diagnostics.integrity_warnings(self.analysis, base, spell=spell)

    def get_metadata(self) -> Dict[str, Any]:
        return self._analysis_view().get_metadata()

    def _scan_budget_dict(self) -> Dict[str, Any]:
        return self._analysis_view()._scan_budget_dict()

    def _row_files(self, graph: ImportGraph) -> set:
        return self._analysis_view()._row_files(graph)

    def _cycle_groups(self, graph: ImportGraph) -> List[List[Path]]:
        return self._analysis_view()._cycle_groups(graph)

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for imports:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return {
            'adapter': 'imports',
            'description': 'Import graph analysis for detecting unused imports, circular dependencies, and layer violations',
            'uri_syntax': 'imports://<path>[?query]',
            'query_params': _SCHEMA_QUERY_PARAMS,
            'elements': {},
            'cli_flags': ['--verbose'],
            'execution_policy': {'default_fail_on': ImportsAdapter.DEFAULT_FAIL_ON,
                                 'fail_on': list(ImportsAdapter.FINDINGS_POLICIES)},
            'supports_batch': False,
            'supports_advanced': False,
            'supported_languages': get_supported_languages(),
            'output_types': _SCHEMA_OUTPUT_TYPES,
            'example_queries': _SCHEMA_EXAMPLE_QUERIES,
            'notes': _SCHEMA_NOTES,
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for imports:// adapter.

        Help data loaded from reveal/adapters/help_data/imports.yaml
        to improve consistency and maintainability.
        """
        help_data = load_help_data('imports') or {}
        # Add dynamic supported languages to help data
        if help_data:
            help_data['supported_languages'] = get_supported_languages()
        return help_data

    def _build_graph(self, target_path: Path, on_file_processed: Optional[Callable[[Path], None]] = None,
                     collect_structures: bool = False) -> None:
        """Build through the public analysis operation, then retain only this request's state."""
        self._scan = scan = _scan_root_of(self._query_params, target_path)
        self._test_layout = TestLayout.for_path(target_path, fallback_root=scan.root,
                                                root_override=scan.override_used)
        from ..config import RevealConfig
        self._test_layout = RevealConfig.get(self._test_layout.anchor).apply_test_layout(self._test_layout)
        self._scan_budget = ScanBudget(_MAX_FILES.read(self._query_params))
        supported = self._parse_extensions if self._parse_extensions is not None else frozenset(get_all_extensions())
        code = frozenset() if self._parse_extensions is not None else get_code_extensions()
        reader = None
        if collect_structures:
            from .ast.analysis import analyze_file_outcome
            reader = analyze_file_outcome
        built = import_analysis.analyze(import_analysis.ScanScope(
            scan.root, supported, code, cap=self._scan_budget.limit,
            focus=None if scan.root == target_path else target_path),
            on_file_processed=on_file_processed, structure_reader=reader)
        self.analysis = built.analysis
        self._structures = built.structures
        self._scope_hidden = hidden_entries_warning(built.files.hidden, built.files.analyzed)

    @staticmethod
    def _discover_candidate_files(target_path: Path, supported_exts: frozenset, code_exts: frozenset, *,
                                  traversal_failures=None, hidden=None):
        """Compatibility discovery entry point; the service owns the walk."""
        files = import_analysis.discover(import_analysis.ScanScope(target_path, supported_exts, code_exts))
        if traversal_failures is not None:
            traversal_failures.extend(files.traversal_failures)
        if hidden is not None:
            hidden.update(files.hidden)
        return list(files.candidates), files.index

    def _analysis_view(self, *, include_top: bool = False) -> ImportView:
        target = self._target_path
        scan = self._scan
        lazy = self._query_params.get(_LAZY.name)
        top = self._query_params.get('top') if include_top else None
        return ImportView(self.analysis, target, scan, self._scan_budget.limit,
                          lazy=None if lazy is None else _LAZY.validate(lazy),
                          tests=_TESTS.read(self._query_params), scope=_SCOPE.read(self._query_params),
                          top=int(top) if top else None, test_layout=self._test_layout)

    def _build_response(self, response_type: str, **data_fields) -> Dict[str, Any]:
        """Build standardized adapter response with common structure.

        Args:
            response_type: Type of response (e.g., 'imports', 'unused_imports')
            **data_fields: Data fields to include in response

        Returns:
            Standardized response dict with contract_version, type, source, etc.
        """
        display = self._display()
        # Keep legacy file/worker diagnostics in their existing metadata and text paths.
        warnings = [warning for warning in self.integrity_warnings(spell=display)
                    if warning.get('type') == 'analysis_incomplete']
        if self._scope_hidden:
            warnings.append(self._scope_hidden)
        warnings.extend(self._scan_warnings())
        response = ResultBuilder.create(
            result_type=response_type,
            source=str(self._target_path),
            source_type='directory' if self._target_path and self._target_path.is_dir() else 'file',
            contract_version=CONTRACT_VERSION,
            data=data_fields,
            warnings=warnings,
        )
        response['metadata'] = metadata = _spell_metadata_paths(self.get_metadata(), display)
        failed = metadata.get('files_failed')
        if isinstance(failed, list):
            # get_metadata keeps the first 50 paths; the count is exact (BACK-1551).
            note_truncation(response, 'metadata.files_failed', len(failed),
                            metadata['files_failed_count'], 'auto_cap',
                            hint='the first 50 by path; files_failed_count is exact')
        return response

    def _display(self) -> Callable[[Optional[str]], Optional[str]]:
        """How this answer spells a path (``_path_display``): every view's rows and its envelope."""
        return _path_display(self._target_path or Path('.').resolve())

    def _lazy_mode(self, default: str) -> Tuple[str, bool]:
        """The &lazy value this view applies, and whether it is the view's ``default``."""
        raw = self._query_params.get(_LAZY.name)  # a read: the view applies it
        return (default, True) if raw is None else (_LAZY.validate(raw), False)

    def _graph(self) -> ImportGraph:
        return self._analysis_view()._graph()

    def _edges(self, default: str) -> ImportGraph:
        return self._analysis_view()._edges(default)

    def outside_root_edge_count(self) -> int:
        return self._analysis_view().outside_root_edge_count()

    def _tests_excluded(self) -> bool:
        return self._analysis_view()._tests_excluded()

    def _scope_is_root(self) -> bool:
        return self._analysis_view()._scope_is_root()

    def _base_dir(self) -> Path:
        return self._analysis_view()._base_dir()

    def _in_scope(self, path: Path) -> bool:
        return self._analysis_view()._in_scope(path)

    def _resolved_at(self, cycles: bool = False) -> import_analysis.ResolvedAt:
        return self._analysis_view()._resolved_at(cycles)

    def _edge_rule(self, default: str, subject: str, *, tests_counted: bool = True,
                   cycles: bool = False) -> Dict[str, Any]:
        return self._analysis_view()._edge_rule(default, subject, tests_counted=tests_counted, cycles=cycles)

    def _format_all(self) -> Dict[str, Any]:
        """Format all imports (default view)."""
        if not self.analysis.graph:
            return {'imports': []}

        view = self._analysis_view()
        imports_by_file = {
            str(file_path): [self._format_import(stmt) for stmt in imports]
            for file_path, imports in self.analysis.graph.files.items() if view._in_scope(file_path)
        }

        return self._build_response(
            'imports', files=imports_by_file,
            edge_rule=view._edge_rule(LAZY_EXCLUDE, 'Cycles Found uses static imports between', cycles=True))

    def _format_fan_in(self) -> Dict[str, Any]:
        data = self._analysis_view(include_top=True).fan_in()
        response = self._build_response('fan_in_ranking', **data)
        note_truncation(response, 'entries', len(data['entries']), data['total'], 'limit', hint='raise ?top=N')
        return response

    def _format_entrypoints(self) -> Dict[str, Any]:
        data = self._analysis_view().entrypoints()
        warnings = data.pop('metadata', {})
        response = self._build_response('entrypoints', **data)
        response['metadata'].update(warnings)
        return response

    def _format_components(self) -> Dict[str, Any]:
        return self._build_response('components', **self._analysis_view().components())

    def _format_external(self) -> Dict[str, Any]:
        """The package table of the imports under the path (``classify.package_table``; deps://
        computed it in its text renderer only, BACK-1054): uses per unresolved and stdlib package."""
        if not self.analysis.graph:
            return self._build_response('external_packages', external_packages=[], stdlib_packages=[],
                                        internal_imports=0, total_imports=0, total_files=0, top_importers=[])
        view = self._analysis_view()
        excluded = view._tests_excluded()
        files = {str(path): [self._format_import(stmt) for stmt in imports]
                 for path, imports in self.analysis.graph.files.items()
                 if view._in_scope(path) and not (excluded and view.is_test(path))}
        table = package_table(files, view._base_dir())
        languages = table['external_package_languages']
        response = self._build_response(
            'external_packages',
            total_imports=table['total_imports'], total_files=table['total_files'],
            internal_imports=table['relative_count'],
            external_packages=[{'package': name, 'uses': uses, 'languages': languages.get(name, [])}
                               for name, uses in table['external_packages']],
            stdlib_packages=[{'package': name, 'uses': uses} for name, uses in table['stdlib_packages']],
            top_importers=[{'file': row['file'], 'imports': row['count']} for row in table['top_importers']],
        )
        assert view.test_layout is not None
        response['metadata']['test_scope'] = view.test_scope()
        return response

    def _format_unused(self) -> Dict[str, Any]:
        """Format unused imports."""
        if not self.analysis.graph:
            return {'unused': []}

        view = self._analysis_view()
        unused = [(stmt, names) for stmt, names in
                  self.analysis.graph.find_unused_imports(self.analysis.symbols_by_file)
                  if view._in_scope(stmt.file_path)]

        # `unused_names` narrows a partly-used `from x import a, b` to the names
        # actually unused (BACK-1066); `count` is statements, like `unused`.
        return self._build_response(
            'unused_imports',
            unused=[{**self._format_import(stmt), 'unused_names': names} for stmt, names in unused],
            count=len(unused)
        )

    def _format_circular(self) -> Dict[str, Any]:
        if self.analysis.graph is None:
            return {'cycles': []}
        return self._build_response('circular_dependencies', **self._analysis_view().circular())

    def _format_violations(self) -> Dict[str, Any]:
        """Format layer violations using .reveal.yaml layer rules."""
        layer_config = load_layer_config(self._target_path)

        if layer_config is None:
            return self._build_response(
                'layer_violations',
                violations=[],
                count=0,
                note='Layer violation detection requires .reveal.yaml configuration'
            )

        view = self._analysis_view()
        project_root = self._target_path if self._target_path.is_dir() else self._target_path.parent
        violations = []

        for from_file, to_files in view._edges(LAZY_INCLUDE).dependencies.items():
            if not view._in_scope(from_file):
                continue
            for to_file in to_files:
                result = layer_config.check_import(from_file, to_file, project_root)
                if result is not None:
                    layer_name, reason = result
                    violations.append({
                        'from_file': to_posix(from_file.relative_to(project_root) if from_file.is_relative_to(project_root) else from_file),
                        'to_file': to_posix(to_file.relative_to(project_root) if to_file.is_relative_to(project_root) else to_file),
                        'layer': layer_name,
                        'reason': reason or f'{layer_name} layer violation',
                    })

        return self._build_response(
            'layer_violations',
            violations=violations,
            count=len(violations),
            edge_rule=view._edge_rule(LAZY_INCLUDE, 'violations check static imports between'),
        )

    def _scan_warnings(self) -> List[WarningEntry]:
        """A refused ?root= (the climb decided instead) and a walk the file cap cut short."""
        warnings: List[WarningEntry] = []
        if self._scan is not None and self._scan.override_rejected:
            warnings.append(cast(WarningEntry, {
                'type': 'root_rejected', 'field': 'root',
                'message': f"{self._scan.override_rejected}; resolved at the scan root the climb found instead"}))
        record = self.analysis.resolution
        if record is not None and record.capped:
            warnings.append(cast(WarningEntry, {
                'type': 'scan_capped', 'field': 'max_files', 'limit': self._scan_budget.limit,
                'message': (f"the walk kept {self._scan_budget.limit:,} source files (max_files) and stopped: "
                            "files past the cap are neither importers nor rows, so counts can under-report; "
                            "raise &max_files=N or narrow &root=")}))
        return warnings

    def _format_importers(self, importers: Any) -> Dict[str, Any]:
        """``?importers``: who imports what, from the edges every other view counts.

        A file (the requested file, or ``=FILE`` relative to the requested directory) lists each
        importer with the statement behind the edge (``resolution.ProjectResolution.edge_statements``),
        its scope and the cascade stage (via) that found it; a package-granularity language (Go)
        also counts importers of the file's directory (BACK-553). Otherwise every module under the
        path with at least one importer, with the sorted importers: the depends:// directory answer.
        """
        target = self._target_path or Path('.').resolve()
        if isinstance(importers, str):
            named, problem = self._named_importers_target(importers)
            if named is None:
                return self._build_response('importer_summary', error=problem, usage=True)
            target = named
        if target.is_file():
            return self._format_file_importers(target)
        view = self._analysis_view()
        graph = view._edges(LAZY_INCLUDE)
        entries = [
            {'file': str(f), 'fan_in': len(sources), 'importers': sorted(str(src) for src in sources)}
            for f, sources in graph.reverse_deps.items() if sources and view._in_scope(f)
            and (target == self._target_path or resolution.path_is_under(f, target))
        ]
        entries.sort(key=lambda e: (-cast(int, e['fan_in']), str(e['file'])))
        return self._build_response(
            'importer_summary', entries=entries, total=len(entries),
            edge_rule=view._edge_rule(LAZY_INCLUDE, 'importers are files whose static imports resolve here, among'))

    def _named_importers_target(self, name: str) -> Tuple[Optional[Path], str]:
        """The file or directory ``?importers=NAME`` names, or ``(None, why)``: a name that matches
        nothing is a usage error, never the directory summary (surface plan rule 9, BACK-2161).

        NAME is tried relative to the requested path and relative to the scan root; a name that
        exists under both and differs is ambiguous, and absolute paths are taken as given."""
        root = self._scan.root if self._scan else self._base_dir()
        found = _named_candidates(name, self._base_dir(), root)
        if len(found) == 1:
            return found[0], ''
        show = _path_display(self._base_dir())  # BACK-2250: the root is a host path in an error text
        if found:
            return None, (f'importers={name} is ambiguous: it names {" and ".join(str(show(str(f))) for f in found)}; '
                          f'spell the path from the scan root {show(str(root))}')
        known = {os.path.relpath(f, root): f for f in self._edges(LAZY_INCLUDE).dependencies}
        near = difflib.get_close_matches(name, [to_posix(k) for k in known], n=3, cutoff=0.5)
        hint = f'; did you mean {", ".join(near)}?' if near else ''
        return None, f'importers={name} matched no file under the scan root ({show(str(root))}){hint}'

    def _format_file_importers(self, target: Path) -> Dict[str, Any]:
        graph = self._edges(LAZY_INCLUDE)
        record = self.analysis.resolution
        statements = record.edge_statements if record is not None else {}
        rows = []
        for src, key, stmt in resolution.file_importers(graph, statements, target):
            row: Dict[str, Any] = {'file': str(src), 'line': 0, 'module': '', 'names': [], 'type': 'unknown',
                                   'is_relative': False, 'alias': None}
            if stmt is not None:
                row.update({'line': stmt.line_number, 'module': stmt.module_name, 'names': stmt.imported_names,
                            'type': stmt.import_type, 'is_relative': stmt.is_relative, 'alias': stmt.alias})
            if row['module'] and os.path.isabs(row['module']):
                row['module'] = to_posix(os.path.relpath(row['module'], self._base_dir()))
            row['scope'] = sorted(s for s in graph.edge_scopes.get(key, ()) if s) or None
            row['via'] = sorted(graph.edge_via.get(key, ())) or None
            rows.append(row)
        return self._build_response(
            'module_importers', target=str(target), importers=rows, count=len(rows),
            edge_rule=self._edge_rule(LAZY_INCLUDE, 'importers are files whose static imports resolve here, among'))

    def _get_local_names(self) -> frozenset:
        """Local package names for the scanned root, computed once (BACK-1190)."""
        if self._local_names_cache is None:
            self._local_names_cache = local_package_names(self._target_path or Path('.'))
        return self._local_names_cache

    def _get_project_namespaces(self) -> set:
        """Declared namespace/package inventory for the scanned files,
        computed once (BACK-1234) -- consulted by ``_format_import`` via
        each file's ``is_intra_project_import`` for languages that need it
        (C#/Java/Kotlin/PHP); ignored by extractors that don't."""
        if self._project_namespaces_cache is None:
            self._project_namespaces_cache = build_project_namespaces(list(self.analysis.scanned_files))
        return self._project_namespaces_cache

    def _format_import(self, stmt: ImportStatement) -> Dict[str, Any]:
        """Format single import statement for output."""
        resolved = str(stmt.resolved_path) if stmt.resolved_path else None
        # BACK-1234: only worth asking the extractor for an is_intra_project_import
        # verdict when resolution truth (above) hasn't already settled it --
        # a resolved/relative import is intra-project by definition and never
        # reaches this extra call.
        is_intra: Optional[bool] = None
        if not (stmt.is_relative or resolved):
            extractor = get_extractor(stmt.file_path)
            if extractor:
                is_intra = extractor.is_intra_project_import(
                    stmt, self._target_path or Path('.'),
                    project_namespaces=self._get_project_namespaces(),
                )
        return {
            'file': str(stmt.file_path),
            'line': stmt.line_number,
            'module': stmt.module_name,
            'names': stmt.imported_names,
            'type': stmt.import_type,
            'is_relative': stmt.is_relative,
            'alias': stmt.alias,
            # BACK-1193: real in-tree file resolve_import() resolved this import
            # to, or None if it did not resolve. None is NOT a claim the module
            # is external/stdlib — it may also be an unresolved local (missing
            # file_index coverage, monorepo/load-path boundary).
            'resolved': resolved,
            # BACK-1190: 'intra_project' | 'stdlib' | 'unresolved' | 'unknown'.
            # Classified on resolution truth (above) first; a 'stdlib' verdict
            # requires a language-appropriate list -- Python's list is never
            # used as a fallback classifier for another language (BACK-1193).
            'classification': classify_import(
                stmt.module_name, stmt.is_relative, resolved,
                family_for_path(str(stmt.file_path)), self._get_local_names(),
                is_intra=is_intra,
            ),
        }


__all__ = ['ImportsAdapter']
