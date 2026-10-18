"""deps:// adapter - dependency health dashboard.

Scan logic lives here; returned text bodies live in rendering/adapters/deps.py (BACK-901/BACK-956); `cli/commands/deps.py` is a
thin argparse shim over this adapter, matching the URI/adapter contract every
other capability follows.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reveal.reveal_types import CONTRACT_VERSION

from .base import ResourceAdapter, register_adapter, register_renderer
from .imports import ImportsAdapter
from ..analyzers.imports.classify import (
    classify_module as _classify_module,
    local_package_names as _local_package_names,
)
from ..conventions import family_for_path
from ..utils.path_utils import _language_for_path
from ..utils.query_parser import CliBinding, ParamSpec, QueryParams, ResourceSpec, nonnegative_display_limit, param_schema
from ..utils.query_binding import bind_declared_params, boolean_value
from ..rendering.adapters.deps import DepsRenderer
from ..utils.results import AnalysisCompleteness, ExecutionFacts, ResultBuilder, merge_execution_facts, result_execution_facts

# BACK-1190: the stdlib list, local-package heuristic, and classifier itself
# now live in reveal/analyzers/imports/classify.py -- shared with
# imports://'s own 'classification' field so the two adapters can't drift
# apart the way BACK-1193 found them having already done.


# ── Data collectors ────────────────────────────────────────────────────────────

def _run_base(adapter: 'DepsAdapter', path: Path) -> Dict[str, Any]:
    """Fetch base import map via ImportsAdapter."""
    result = adapter.compose(ImportsAdapter, str(path), default={})
    adapter._record_component('base', result)
    return result if isinstance(result, dict) and _valid_component_payload('base', result) else {}


def _run_circular(adapter: 'DepsAdapter', path: Path) -> Dict[str, Any]:
    """Fetch circular dependency cycles via ImportsAdapter."""
    result = adapter.compose(ImportsAdapter, str(path), default={}, query='circular')
    adapter._record_component('circular', result)
    return result if _valid_component_payload('circular', result, require_count=False) else {}


def _run_unused(adapter: 'DepsAdapter', path: Path) -> List[Dict[str, Any]]:
    """Fetch unused imports via ImportsAdapter."""
    data = adapter.compose(ImportsAdapter, str(path), default={}, query='unused')
    adapter._record_component('unused', data)
    return data['unused'] if _valid_component_payload('unused', data, require_count=False) else []


def _valid_import_entries(entries: Any) -> bool:
    return isinstance(entries, list) and all(isinstance(entry, dict) for entry in entries)


def _valid_component_payload(name: str, result: Any, *, require_count: bool = True) -> bool:
    """Validate collections/counts consumed by the dashboard, not import internals."""
    if not isinstance(result, dict):
        return False
    if name == 'base':
        files = result.get('files')
        return isinstance(files, dict) and all(_valid_import_entries(entries) for entries in files.values())
    values = result.get('cycles' if name == 'circular' else 'unused')
    if not isinstance(values, list):
        return False
    count = result.get('count')
    if require_count and (type(count) is not int or count != len(values)):
        return False
    if name == 'circular':
        return all(isinstance(cycle, list) and all(isinstance(file, str) for file in cycle)
                   for cycle in values)
    return _valid_import_entries(values)


def _component_counts(metadata: Any) -> Optional[Tuple[int, int]]:
    if not isinstance(metadata, dict):
        return None
    failed, lost = metadata.get('files_failed_count'), metadata.get('files_lost_count')
    if type(failed) is not int or type(lost) is not int or not 0 <= lost <= failed:
        return None
    return failed, lost


def _component_diagnostics(name: str, metadata: Any, meta: Dict[str, Any]) -> Dict[str, Any]:
    diagnostics = {key: deepcopy(metadata[key])
                   for key in ('files_failed', 'files_lost', 'extraction_diagnostics')
                   if isinstance(metadata, dict) and key in metadata}
    for warning in meta.get('warnings', []):
        field = warning.get('field', '')
        if warning.get('type') == 'truncated' and field.removeprefix('metadata.') in diagnostics:
            target = f'analysis.components.{name}.diagnostics.{field.removeprefix("metadata.")}'
            # compose folds the same entry: keep exact counts/cause and hint text.
            warning['field'] = target
            if isinstance(warning.get('message'), str):
                warning['message'] = warning['message'].replace(field, target)
    for key in ('warnings', 'errors'):
        if meta.get(key):
            diagnostics[key] = deepcopy(meta[key])
    return diagnostics


def _component_state(name: str, result: Dict[str, Any], counts: Optional[Tuple[int, int]],
                     meta: Dict[str, Any]) -> AnalysisCompleteness:
    if result.get('error') or counts is None or not _valid_component_payload(name, result):
        return AnalysisCompleteness.FAILED
    missing = any(w.get('type') in ('partial_parse', 'worker_lost', 'analysis_failed', 'parse_recovered', 'analysis_incomplete')
                  for w in meta.get('warnings', []))
    if any(counts) or meta.get('errors') or missing:
        return AnalysisCompleteness.INCOMPLETE
    return AnalysisCompleteness.COMPLETE


def _observed_import(entry: Dict[str, Any]) -> bool:
    names = entry.get('names')
    relative = (entry.get('is_relative') is True and isinstance(names, list) and bool(names)
                and all(isinstance(name, str) and bool(name) for name in names))
    return (isinstance(entry.get('file'), str) and bool(entry['file'])
            and type(entry.get('line')) is int and entry['line'] > 0
            and (isinstance(entry.get('module'), str) and bool(entry['module']) or relative))


def _observed_dependencies(base, circular, unused) -> bool:
    imports = [entry for entries in base.get('files', {}).values() for entry in entries]
    cycles = circular.get('cycles', [])
    return (any(_observed_import(entry) for entry in [*imports, *unused])
            or any(len(set(path for path in cycle if path)) >= 2 for cycle in cycles))


def _deps_top(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError('top requires a whole number, not a bare boolean')
    return nonnegative_display_limit(value)


_TOP = ParamSpec('top', 'integer', 'Items per text section (JSON retains all)', 10,
                 _deps_top, ('top=15',), minimum=0, zero_policy='no text entries',
                 role='presentation', cli=CliBinding(('--top',), metavar='N'))
_NO_UNUSED = ParamSpec('no_unused', 'boolean', 'Skip unused-import analysis', False,
                       boolean_value, ('no_unused=true',), role='analysis',
                       cli=CliBinding(('--no-unused',), action='store_true'))
_NO_CIRCULAR = ParamSpec('no_circular', 'boolean', 'Skip circular-dependency analysis', False,
                         boolean_value, ('no_circular=true',), role='analysis',
                         cli=CliBinding(('--no-circular',), action='store_true'))
_SUMMARY_ONLY = ParamSpec('summary_only', 'boolean', 'Primary JSON only: replace base.files with counts',
                          False, boolean_value, ('summary_only=true',), role='presentation',
                          cli=CliBinding(('--summary-only',), action='store_true'))


def _summarize_base_files(result: dict) -> dict:
    """Replace the full base import map with its counts after execution facts exist."""
    base = result.get('base')
    if not isinstance(base, dict) or not isinstance(base.get('files'), dict):
        return result
    files = base['files']
    summary = {key: value for key, value in base.items() if key != 'files'}
    summary['total_files'] = len(files)
    summary['total_imports'] = sum(len(value) for value in files.values())
    return {**result, 'base': summary}


def _finding_count_valid(value: Any, state: str) -> bool:
    return (value is None and state == 'failed') or (type(value) is int and value >= 0)


def _component_proof_error(component: Any, finding: Any = 0) -> Optional[str]:
    if not isinstance(component, dict):
        return 'Required component record is missing or malformed'
    state = component.get('completeness')
    if state not in ('complete', 'incomplete', 'failed'):
        return 'Required component completeness is missing or malformed'
    if 'files_failed_count' not in component or 'files_lost_count' not in component:
        return 'Required component failed/lost counts are missing'
    failed, lost = component.get('files_failed_count'), component.get('files_lost_count')
    known_counts = type(failed) is int and type(lost) is int and 0 <= lost <= failed
    unknown_counts = failed is None and lost is None and state == 'failed'
    if not known_counts and not unknown_counts:
        return 'Required component failed/lost counts are missing or malformed'
    if not _finding_count_valid(finding, state):
        return 'Required findings count is missing or malformed'
    if state == 'complete' and failed:
        return 'Complete component contradicts missing-input counts'
    return None


def _deps_component_keys_error(analysis: Dict[str, Any], skipped: Any) -> Optional[str]:
    if not isinstance(skipped, list) or any(name not in ('circular', 'unused') for name in skipped):
        return 'Deps skipped-component evidence is malformed'
    if len(set(skipped)) != len(skipped):
        return 'Deps skipped-component evidence is duplicated'
    components, findings = analysis.get('components'), analysis.get('findings')
    required = {'base', 'circular', 'unused'} - set(skipped)
    if not isinstance(components, dict) or set(components) != required:
        return 'Deps answer missing exact required component evidence'
    if not isinstance(findings, dict) or set(findings) != required - {'base'}:
        return 'Deps answer missing exact required findings evidence'
    return None


def _deps_proof_error(result: Any) -> Optional[str]:
    if not isinstance(result, dict):
        return 'Required deps answer is malformed'
    analysis = result.get('analysis')
    if not isinstance(analysis, dict) or type(analysis.get('complete')) is not bool:
        return 'Deps answer missing required completeness evidence'
    error = _deps_component_keys_error(analysis, result.get('skipped'))
    if error:
        return error
    components, findings = analysis['components'], analysis['findings']
    for name, component in components.items():
        error = _component_proof_error(component, findings.get(name, 0))
        if error:
            return f'{name}: {error}'
    complete = all(component['completeness'] == 'complete' for component in components.values())
    if analysis['complete'] != complete:
        return 'Deps aggregate completeness contradicts required component evidence'
    return None


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
    RESULT_TYPE = 'deps_scan'
    FINDINGS_POLICIES = ('none', 'findings')
    DEFAULT_FAIL_ON = 'none'
    RESOURCE_SPEC = ResourceSpec(uri_codec='existing-path-first')
    PARAM_SPECS = (_TOP, _NO_UNUSED, _NO_CIRCULAR, _SUMMARY_ONLY)

    def _record_component(self, name: str, result: Any) -> None:
        """Retain required evidence before the unused child becomes a plain list."""
        result = result if isinstance(result, dict) else {}
        metadata = result.get('metadata')
        counts = _component_counts(metadata)
        meta = result.get('meta') or {}
        diagnostics = _component_diagnostics(name, metadata, meta)
        state = _component_state(name, result, counts, meta)
        if state is AnalysisCompleteness.FAILED:
            self.__dict__.setdefault('_composed_errors', []).append({
                'code': 'E_DEPS_COMPONENT', 'component': name,
                'message': str(result.get('error') or 'Required imports payload or failed/lost input counts are missing or malformed'),
            })
        record = {'completeness': state.value, 'files_failed_count': counts[0] if counts else None,
                  'files_lost_count': counts[1] if counts else None, 'diagnostics': diagnostics}
        self.__dict__.setdefault('_deps_components', {})[name] = record
        if name != 'base':
            field = 'cycles' if name == 'circular' else 'unused'
            count = len(result[field]) if _valid_component_payload(name, result, require_count=False) else None
            self.__dict__.setdefault('_deps_findings', {})[name] = count

    def __init__(self, resource: str, query: Optional[str] = None, *, params: Optional[Dict[str, Any]] = None):
        self.path = str(Path(resource).expanduser())
        if params is not None:
            self.query_params = params if isinstance(params, QueryParams) else bind_declared_params(
                self.PARAM_SPECS, params, transport='typed')
        else:
            self.query_params = bind_declared_params(self.PARAM_SPECS, query or '', transport='uri')
        self._warn_unknown_query_params(self.query_params)  # BACK-507

    @staticmethod
    def answer_requirement_error(result, expected_type, prior_facts=None):
        return _deps_proof_error(result)

    @staticmethod
    def execution_facts(result):
        if _deps_proof_error(result):
            return result_execution_facts(result, completeness=AnalysisCompleteness.FAILED)
        analysis = result['analysis']
        facts = merge_execution_facts(*(ExecutionFacts(AnalysisCompleteness(component['completeness']))
                                        for component in analysis['components'].values()))
        meta = result.get('meta') or {}
        missing = bool(meta.get('errors')) or any(
            warning.get('type') in ('partial_parse', 'worker_lost', 'analysis_failed', 'parse_recovered', 'analysis_incomplete')
            for warning in meta.get('warnings', []))
        if missing:
            facts = merge_execution_facts(facts, ExecutionFacts(AnalysisCompleteness.INCOMPLETE))
        return result_execution_facts(
            result, completeness=facts.completeness,
            findings=any(count is not None and count > 0 for count in analysis['findings'].values()))

    def post_process(self, result, args):
        if getattr(args, 'format', 'text') == 'json' and _SUMMARY_ONLY.read(self.query_params):
            return _summarize_base_files(result)
        return result

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
                'Default --fail-on none reports completed findings without failing; '
                '--fail-on findings exits 1 for circular groups or unused imports. '
                'Required analysis/output failures exit 3; invalid requests exit 2.',
                'summary_only applies only to primary JSON; text and its JSON artifact retain base.files. '
                'top affects text only (0 shows none); --verbose expands text, and URI --all also expands text.',
                'Not depends:// (one character apart) — deps:// is a dashboard '
                'over the whole tree; depends:// answers "who imports this one '
                'module" for a single target.',
                'Both forms use contract v1.1 and result type deps_scan. analysis retains required '
                'component completeness and uncapped findings counts.',
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
            'uri_syntax': 'deps://<path>?top=10&no_unused=true&no_circular=true&summary_only=true',
            'resource': DepsAdapter.RESOURCE_SPEC.schema(),
            'execution_policy': {'default_fail_on': 'none', 'fail_on': ['none', 'findings']},
            'query_params': param_schema(DepsAdapter.PARAM_SPECS),
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
                            'analysis': {'type': 'object', 'description': 'Required component completeness, exact failed/lost input counts and uncapped findings counts'},
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
        self._clear_request_evidence()
        try:
            return self._get_structure()
        finally:
            # A request that fails before construction must not contaminate reuse.
            self._clear_request_evidence()

    def _clear_request_evidence(self) -> None:
        self._deps_components: Dict[str, Dict[str, Any]] = {}
        self._deps_findings: Dict[str, Optional[int]] = {}
        self._composed_errors = []
        self._composed_warnings = []
        self._composed_confidences = []

    def _qualify_directory_loss(self, base, circular, unused) -> None:
        """An inaccessible population cannot establish absence of dependencies."""
        affected = [name for name, record in self._deps_components.items()
                    if any(w.get('type') == 'analysis_incomplete'
                           for w in record['diagnostics'].get('warnings', []))]
        if not affected:
            return
        valid = {name for name, record in self._deps_components.items()
                 if record['completeness'] != AnalysisCompleteness.FAILED.value}
        base = base if 'base' in valid else {}
        circular = circular if 'circular' in valid else {}
        unused = unused if 'unused' in valid else []
        if _observed_dependencies(base, circular, unused):
            return
        for name in affected:
            record = self._deps_components[name]
            record['completeness'] = AnalysisCompleteness.FAILED.value
            self._composed_errors.append({
                'code': 'E_DEPS_COMPONENT', 'component': name,
                'message': 'Required directory discovery failed and no dependency observations survived',
            })

    def _get_structure(self) -> Dict[str, Any]:
        path = Path(self.path)
        no_unused = _NO_UNUSED.read(self.query_params)
        no_circular = _NO_CIRCULAR.read(self.query_params)

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

        components = self._deps_components
        required = ['base', *[name for name in ('circular', 'unused') if name not in report['skipped']]]
        for name in required:
            if name not in components:
                self._record_component(name, {})
        self._qualify_directory_loss(base, circular, unused)
        facts = merge_execution_facts(*(ExecutionFacts(AnalysisCompleteness(record['completeness']))
                                        for record in components.values()))
        report['analysis'] = {'complete': facts.completeness is AnalysisCompleteness.COMPLETE,
                              'components': components, 'findings': self._deps_findings}

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
