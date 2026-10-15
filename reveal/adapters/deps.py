"""deps:// adapter - dependency health dashboard.

Scan logic lives here; returned text bodies live in rendering/adapters/deps.py (BACK-901/BACK-956); `cli/commands/deps.py` is a
thin argparse shim over this adapter, matching the URI/adapter contract every
other capability follows.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from reveal.reveal_types import CONTRACT_VERSION

from .base import ResourceAdapter, register_adapter, register_renderer
from .imports import ImportsAdapter
from ..analyzers.imports.classify import (
    classify_module as _classify_module,
    local_package_names as _local_package_names,
)
from ..conventions import family_for_path
from ..utils.path_utils import _language_for_path
from ..utils.query import parse_query_params
from ..rendering.adapters.deps import DepsRenderer
from ..utils.results import ResultBuilder

# BACK-1190: the stdlib list, local-package heuristic, and classifier itself
# now live in reveal/analyzers/imports/classify.py -- shared with
# imports://'s own 'classification' field so the two adapters can't drift
# apart the way BACK-1193 found them having already done.


# ── Data collectors ────────────────────────────────────────────────────────────

def _run_base(adapter: 'DepsAdapter', path: Path) -> Dict[str, Any]:
    """Fetch base import map via ImportsAdapter."""
    return adapter.compose(ImportsAdapter, str(path), default={})


def _run_circular(adapter: 'DepsAdapter', path: Path) -> Dict[str, Any]:
    """Fetch circular dependency cycles via ImportsAdapter."""
    return adapter.compose(ImportsAdapter, str(path), default={}, query='circular')


def _run_unused(adapter: 'DepsAdapter', path: Path) -> List[Dict[str, Any]]:
    """Fetch unused imports via ImportsAdapter."""
    data = adapter.compose(ImportsAdapter, str(path), default={}, query='unused')
    return data.get('unused', [])


def _relativize_deps_paths(
    base: Dict[str, Any],
    circular: Dict[str, Any],
    unused: List[Dict[str, Any]],
    base_path: Path,
) -> None:
    """Relativize the file-path fields the text renderer already relativizes
    (`_render_circular`/`_render_unused`/`_analyse_imports`'s `to_relative_display`
    calls), but in the raw structures get_structure() serializes directly to
    JSON — those never routed through the text renderer, so `--format json`
    leaked absolute host paths (analyst's filesystem layout/username), same
    gap as overview.py's `_relativize_paths` fixes (BACK-1194 follow-up).
    Mutates in place.
    """
    from ..utils.path_utils import to_relative_display

    if base.get('source'):
        base['source'] = to_relative_display(base['source'], base_path)
    files = base.get('files')
    if isinstance(files, dict):
        base['files'] = {
            to_relative_display(fp, base_path): imports
            for fp, imports in files.items()
        }
    for key in ('cycles', 'cycle_paths'):
        groups = circular.get(key)
        if groups:
            circular[key] = [
                [to_relative_display(fp, base_path) for fp in group]
                for group in groups
            ]
    for imp in unused:
        if imp.get('file'):
            imp['file'] = to_relative_display(imp['file'], base_path)


def _tally_import(
    imp: Dict[str, Any], family: str, local_names: frozenset,
    external_counts: Counter, stdlib_counts: Counter,
    external_languages: Optional[Dict[str, set]] = None,
    language: Optional[str] = None,
) -> bool:
    """Classify+count one import; returns True if it counts as internal.

    BACK-1262: *external_languages* accumulates which source language each
    unresolved package was imported from, so a mixed-stack repo's table can say
    whether `react` came from npm and `pydantic` from Python instead of
    interleaving both in one usage-sorted list with no way to tell.
    """
    if imp.get('is_relative') or imp.get('resolved'):
        return True  # syntactically relative, or resolved in-tree (BACK-1193)
    bucket, key = _classify_module(imp.get('module') or '', family, local_names)
    if bucket == 'external' and imp.get('classification') == 'intra_project':
        # BACK-1236: imports://'s own is_intra_project_import verdict (BACK-1234,
        # declared-namespace matching for Go/C#/Java/Kotlin/PHP) upgraded this
        # import past the name-only heuristic above -- honor that here too,
        # rather than still tallying it as an external package.
        return True
    if bucket == 'stdlib':
        stdlib_counts[key] += 1
    elif bucket == 'external':
        external_counts[key] += 1
        if external_languages is not None and language:
            external_languages.setdefault(key, set()).add(language)
    return bucket == 'internal'


def _analyse_imports(files: Dict[str, List[Dict[str, Any]]], base_path: Path) -> Dict[str, Any]:
    """Derive package counts and top importers from the raw files dict.

    BACK-1193: this classifier used to be Python-only in three ways — a
    ``__init__.py``-based local-package heuristic, an unconditional check
    against Python's own stdlib list, and a dot-only module split — applied
    unconditionally to all 18 languages reveal supports. On Ruby it reported
    local files and stdlib modules as "third-party" (`open3`, `fileutils`)
    and manufactured a bogus stdlib count from name collisions with Python
    (`json`, `socket`, ...). Fixed by classifying on resolution truth first:
    ``imports://``'s ``resolved`` field (BACK-1193, real in-tree file or
    None from ``resolve_import()``) is now the primary signal, with the
    ``__init__.py`` heuristic kept only as a fallback for imports resolution
    could not settle. Python-list stdlib is only ever checked for Python
    files — never fall back to Python's list for a non-Python import (task's
    own rule). Dart is the one other language classified as stdlib, because
    its ``dart:`` import prefix (`dart:async`, `dart:io`, ...) is a
    syntactic marker, not a name lookup that could collide the way a bare
    list-membership check would — same rule, no list needed.
    """
    local_names = _local_package_names(base_path)
    external_counts: Counter = Counter()
    external_languages: Dict[str, set] = {}
    stdlib_counts: Counter = Counter()
    relative_count = 0
    importer_counts: Counter = Counter()
    total_imports = 0

    for filepath, imports in files.items():
        if not isinstance(imports, list):
            continue
        importer_counts[filepath] += len(imports)
        total_imports += len(imports)
        family = family_for_path(filepath)
        language = _language_for_path(Path(filepath))
        for imp in imports:
            if _tally_import(
                imp, family, local_names, external_counts, stdlib_counts,
                external_languages=external_languages, language=language,
            ):
                relative_count += 1

    # Top importers as relative paths (BACK-1194: shared resolve()-aware
    # helper — see to_relative_display()'s docstring for why the old
    # lexical-only relative_to() let absolute paths leak through on
    # relative CLI targets)
    from ..utils.path_utils import to_relative_display
    top_importers = []
    for fp, count in importer_counts.most_common():
        rel = to_relative_display(fp, base_path)
        top_importers.append({'file': rel, 'count': count})

    return {
        'total_imports': total_imports,
        'total_files': len(files),
        'relative_count': relative_count,
        'external_packages': external_counts.most_common(),
        'external_package_languages': {
            pkg: sorted(langs) for pkg, langs in external_languages.items()
        },
        'stdlib_packages': stdlib_counts.most_common(),
        'top_importers': top_importers,
    }


@register_adapter('deps')
@register_renderer(DepsRenderer)
class DepsAdapter(ResourceAdapter):
    """Adapter for the dependency health dashboard: external packages,
    circular deps, unused imports — composed from imports://."""
    HELP_CLUSTER = 'Code Analysis'

    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    CLI_QUERY_FLAGS = {'respect_gitignore': 'respect_gitignore=false'}  # --no-gitignore (BACK-1386)
    RESOURCE_IS_PATH = True  # a nonexistent path is an error, not an empty result (BACK-1321)

    def __init__(self, resource: str, query: Optional[str] = None):
        self.path = str(Path(resource).expanduser())
        self.query_params = parse_query_params(query or '', coerce=True)
        self._warn_unknown_query_params(self.query_params)  # BACK-507

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'deps',
            'description': 'Dependency health dashboard: external packages, circular deps, unused imports.',
            'syntax': 'deps://<path>[?top=10&no_unused=true&no_circular=true]',
            'examples': [
                {'uri': 'deps://src', 'description': 'Dependency dashboard for src/'},
                {'uri': 'deps://.?top=15', 'description': 'Top 15 items per section'},
                {'uri': 'deps://.?no_unused=true', 'description': 'Skip the unused-imports section'},
            ],
            'features': [
                'Unresolved (third-party or unresolved-local) package usage '
                'counts — stdlib separated out, Python only (BACK-1193)',
                'Circular dependency cycles',
                'Unused imports',
                'Top importers by file',
            ],
            'notes': [
                'Composed entirely from imports:// — not an independent scan.',
                'Not depends:// (one character apart) — deps:// is a dashboard '
                'over the whole tree; depends:// answers "who imports this one '
                'module" for a single target.',
                'BACK-1178: the CLI subcommand form (`reveal deps <path> --format '
                'json`) and this URI form intentionally carry different '
                'contract_version/meta envelopes — subcommand-form is frozen at '
                'v1.0 with no meta block (BACK-906, backward-compat guarantee for '
                'existing --format json consumers), URI-form is on v1.1 with a '
                'meta block (confidence/warnings/errors, BACK-885/891). The '
                'underlying data fields are otherwise the same.',
            ],
            'see_also': [
                'reveal deps <path> - CLI subcommand form',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'deps',
            'description': 'Dependency health dashboard (external packages, circular deps, unused imports)',
            'uri_syntax': 'deps://<path>?top=10&no_unused=true&no_circular=true',
            'query_params': {
                'top': {'type': 'integer', 'minimum': 0, 'description': 'Number of items to show per section', 'examples': ['top=15']},
                'no_unused': {'type': 'boolean', 'description': 'Skip the unused-imports section', 'examples': ['no_unused=true']},
                'no_circular': {'type': 'boolean', 'description': 'Skip the circular-dependencies section', 'examples': ['no_circular=true']},
            },
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'deps_scan',
                    'description': 'Base import map, circular-dependency cycles, and unused imports',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'base': {'type': 'object'},
                            'circular': {'type': 'object'},
                            'unused': {'type': 'array'},
                            'skipped': {
                                'type': 'array',
                                'description': "Checks turned off by no_circular/no_unused ('circular', 'unused'); "
                                               'their empty result means not checked, not clean',
                            },
                        },
                    },
                },
            ],
            'example_queries': [
                {'uri': 'deps://src', 'description': 'Dependency dashboard for src/', 'output_type': 'deps_scan', 'task': 'quality'},
            ],
            'notes': [
                'Composed from three imports:// queries (base, ?circular, ?unused) — not an independent scan.',
            ],
        }

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        path = Path(self.path)
        no_unused = str(self.query_params.get('no_unused', False)).lower() == 'true'
        no_circular = str(self.query_params.get('no_circular', False)).lower() == 'true'

        base = _run_base(self, path)
        circular = {} if no_circular else _run_circular(self, path)
        unused = [] if no_unused else _run_unused(self, path)
        _relativize_deps_paths(base, circular, unused, path)

        report = {
            'path': str(path),
            'base': base,
            'circular': circular,
            'unused': unused,
            # BACK-1466: an empty circular/unused because the check was turned
            # off must not read as a clean one ({} rendered "✅ no circular deps").
            'skipped': [name for name, off in (('circular', no_circular), ('unused', no_unused)) if off],
        }

        meta = self.composed_meta()
        return ResultBuilder.create(
            result_type='deps_scan',
            source=self.path,
            contract_version=CONTRACT_VERSION,
            data=report,
            warnings=meta.get('warnings') if meta else None,
            errors=meta.get('errors') if meta else None,
            confidence=meta.get('confidence') if meta else None,
        )
