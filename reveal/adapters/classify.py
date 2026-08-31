"""classify:// adapter -- provenance tag for every file in a directory's
full, unranked population (BACK-1233).

BACK-1195 wired 'provenance' tagging into overview://'s/hotspots://'s/
pack://'s RANKED output, but a DD consumer asking "what fraction of this
codebase is first-party" needs the tag over the FULL file population,
independent of any adapter's own ranking or selection -- structurally
uncomputable from any of those three (each only tags whatever subset it
already selects for its own purpose). This reuses BACK-1195's
classify_path_provenance() and stats://'s existing find_analyzable_files()
walker rather than building a new classifier or a new directory walk.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import ResourceAdapter, register_adapter, register_renderer
from .stats.analysis import find_analyzable_files, get_file_display_path
from ..utils import print_json_result
from ..utils.path_utils import classify_path_provenance, looks_vendored_by_banner, is_vendor_dir
from ..utils.query import parse_query_params
from ..utils.results import ResultBuilder
from ..utils.validation import require_path_exists

# BACK-1238: many same-extension siblings in one directory named after
# 2-3 letter language codes (optionally region-tagged, e.g. `en`, `zh-CN`)
# is an unusual pattern for first-party application code, but a common shape
# for vendored i18n bundles (moment.js locales, jQuery Validate messages).
# Threshold picked well above the ticket's real evidence (13-14 locale files
# per vendored library) so a small first-party set of genuinely per-language
# files (e.g. 2-3 fixtures) doesn't false-positive.
_LOCALE_STEM_RE = re.compile(r'^[a-z]{2,3}(-[A-Z]{2})?$')
_LOCALE_FANOUT_THRESHOLD = 5

# BACK-1242: directory names where a project keeps ITS OWN translations by
# Rails/Django/JS convention -- locale fan-out on its own is not a vendor
# signal here (confirmed false-positive: config/locales/*.yml,
# src/renderer/i18n/*.ts both measured as a project's first-party i18n, not
# vendored code). Still eligible if nested under a real vendor directory
# (e.g. vendor/gems/somegem/config/locales) -- see the is_vendor_dir check
# below.
_FIRST_PARTY_I18N_DIR_NAMES = frozenset({
    'locale', 'locales', 'lang', 'langs', 'translations', 'translation', 'i18n', 'l10n',
})


def _apply_locale_fanout(rows: List[Dict[str, Any]]) -> None:
    """Reclassify first_party files as vendor when they're part of a
    locale-file fan-out (BACK-1238) — mutates *rows* in place.

    Structural signal, not a per-file content check: needs every sibling in
    the directory, so it runs as a second pass over the full population
    rather than inline in the per-file loop.
    """
    groups: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rel = Path(row['file'])
        if _LOCALE_STEM_RE.match(rel.stem):
            groups[(rel.parent, rel.suffix)].append(row)
    for (parent, _suffix), group_rows in groups.items():
        if len(group_rows) < _LOCALE_FANOUT_THRESHOLD:
            continue
        parent_parts = parent.parts
        immediate_name = parent_parts[-1].lower() if parent_parts else ''
        if (
            immediate_name in _FIRST_PARTY_I18N_DIR_NAMES
            and not any(is_vendor_dir(p) for p in parent_parts)
        ):
            continue
        for row in group_rows:
            if row['provenance'] == 'first_party':
                row['provenance'] = 'vendor'


def _classify_directory(directory: Path) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Returns (rows, excluded_by_extension).

    BACK-1241: the population here is gated on find_analyzable_files() ->
    get_analyzer() returning a real analyzer -- extensions with no
    registered analyzer anywhere (.erb, .vue, .scss, .css confirmed live)
    are silently absent from both `rows` and its own count, and
    overview://'s total_files agrees by construction (same shared walker),
    not because the population is actually complete. excluded_by_extension
    makes the gap visible instead of reporting a partial population as if
    it were the full one.
    """
    rows = []
    excluded_by_extension: Dict[str, int] = {}
    for file_path in find_analyzable_files(directory, excluded_by_extension=excluded_by_extension):
        rel = Path(get_file_display_path(file_path, directory))
        provenance = classify_path_provenance(rel.parts[:-1], rel.name)
        if provenance is None and looks_vendored_by_banner(file_path):
            provenance = 'vendor'
        rows.append({
            'file': rel.as_posix(),
            'provenance': provenance or 'first_party',
        })
    _apply_locale_fanout(rows)
    return rows, excluded_by_extension


class ClassifyRenderer:
    """Renderer for classify:// results."""

    @staticmethod
    def render_structure(result: Dict[str, Any], format: str = 'text') -> None:
        if format == 'json':
            print_json_result(result)
            return
        rows = result.get('files', [])
        summary = result.get('summary', {})
        print(f"Provenance classification: {result.get('source', '')}")
        print(f"{summary.get('total', len(rows))} files")
        for label, count in summary.get('by_provenance', {}).items():
            print(f"  {label}: {count}")
        excluded = summary.get('excluded', 0)
        if excluded:
            # BACK-1241: the count above is not the full population -- make
            # that visible in text mode too, not just JSON.
            by_ext = summary.get('excluded_by_extension', {})
            top = ', '.join(f"{ext} ({n})" for ext, n in list(by_ext.items())[:5])
            more = f", +{len(by_ext) - 5} more extensions" if len(by_ext) > 5 else ''
            print(f"\n⚠ {excluded} more file(s) not classified — no analyzer for: {top}{more}")
        print()
        for row in rows:
            print(f"  {row['provenance']:>11}  {row['file']}")

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error classifying provenance: {error}")


@register_adapter('classify')
@register_renderer(ClassifyRenderer)
class ClassifyAdapter(ResourceAdapter):
    """Provenance classification (first_party/test/vendor/minified) for
    every file in a directory, independent of any ranking or selection
    (BACK-1233) -- the full-population counterpart to overview://'s/
    hotspots://'s/pack://'s ranked-subset provenance tags (BACK-1195)."""

    HELP_CLUSTER = 'Code Analysis'
    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907

    def __init__(self, resource: str, query: Optional[str] = None):
        self.path = str(Path(resource).expanduser())
        self.query_params = parse_query_params(query or '', coerce=True)
        self._warn_unknown_query_params(self.query_params)  # BACK-507

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'classify',
            'description': 'Provenance tag (first_party/test/vendor/minified) for every ANALYZABLE file in a directory, over the full unranked population of those files.',
            'syntax': 'classify://<dir>',
            'examples': [
                {'uri': 'classify://src', 'description': 'Provenance for every analyzable file under src/'},
            ],
            'features': [
                'One row per file — not a ranked/capped subset like overview://, hotspots://, pack://',
                'Path-only signals (test/vendor-dir/minified) plus two cheap content signals for in-tree vendoring (BACK-1238): a minifier-preserved license banner in the first few lines, and locale-file fan-out (many same-extension siblings named after language codes)',
                'summary.by_provenance gives a first-party-vs-noise fraction for the whole target',
                "summary.excluded/excluded_by_extension (BACK-1241) discloses files skipped for having no registered analyzer at all (.erb/.vue/.scss confirmed common) -- summary.total is the analyzed population, not every file on disk",
            ],
            'notes': [
                "Content-based generated-file detection (checks.py's _is_generated_file) is not folded in.",
                'Content reads are bounded to the first few lines of files not already classified by path alone — overview:///hotspots:///pack:// remain path-only.',
                'Inclusion rule (BACK-1241): a file is in the counted population iff registry.get_analyzer() recognizes its extension -- the same rule overview:///hotspots:///pack:// use for their own totals, which is why those numbers agree with classify:// by construction, not because either is a full-disk count. Template/markup formats without a registered analyzer (.erb, .vue, .scss, .css) are invisible to all of them; check summary.excluded_by_extension before treating summary.total as "the codebase".',
            ],
            'see_also': [
                'reveal hotspots://<dir> - ranked complexity hotspots, each tagged with provenance',
                'reveal overview://<dir> - directory summary, ranked sections tagged with provenance',
            ],
            'output_formats': ['text', 'json'],
        }

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'classify',
            'description': 'Provenance classification for every analyzable file in a directory (see summary.excluded for what has no registered analyzer)',
            'uri_syntax': 'classify://<dir>',
            'query_params': {},
            'elements': {},
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'classify_report',
                    'description': 'One row per analyzable file with its provenance tag, plus a summary count by category',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'files': {'type': 'array'},
                            'summary': {'type': 'object'},
                        },
                    },
                },
            ],
            'example_queries': [
                {'uri': 'classify://src', 'description': 'Provenance for every file under src/', 'output_type': 'classify_report', 'task': 'dd'},
            ],
            'notes': [
                'Mostly path-only classification (directory/filename conventions), plus two bounded content checks for in-tree vendoring (BACK-1238) — see get_help().',
            ],
        }

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        path = Path(self.path)
        require_path_exists(path)

        directory = path if path.is_dir() else path.parent
        rows, excluded_by_extension = _classify_directory(directory)

        by_provenance: Dict[str, int] = {}
        for row in rows:
            by_provenance[row['provenance']] = by_provenance.get(row['provenance'], 0) + 1

        data = {
            'files': rows,
            'summary': {
                'total': len(rows),
                'by_provenance': by_provenance,
                # BACK-1241: `total` above is NOT the full file population --
                # it's only files with a registered analyzer. `excluded`
                # (population - total) plus the per-extension breakdown
                # discloses what's missing (.erb/.vue/.scss and similar
                # unanalyzed-but-real source formats) instead of `total`
                # silently reading as complete coverage.
                'excluded': sum(excluded_by_extension.values()),
                'excluded_by_extension': dict(
                    sorted(excluded_by_extension.items(), key=lambda kv: -kv[1])
                ),
            },
        }

        return ResultBuilder.create(
            result_type='classify_report',
            source=str(path),
            data=data,
        )
