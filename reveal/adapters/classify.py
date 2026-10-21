"""classify:// adapter -- provenance tag for every file in a directory's
full, unranked population (BACK-1233).

The classification, its heuristics and its report are owned by
adapters/stats/provenance.py; this adapter binds the classify:// spelling to it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .base import ResourceAdapter, register_adapter, register_renderer
from .stats.provenance import provenance_report, render_provenance
from ..utils import print_json_result
from ..utils.gitignore import respect_gitignore_param
from ..utils.query import parse_query_params
from ..utils.validation import require_path_exists


class ClassifyRenderer:
    """Renderer for classify:// results."""

    @staticmethod
    def render_structure(result: Dict[str, Any], format: str = 'text') -> None:
        if format == 'json':
            print_json_result(result)
            return
        render_provenance(result)


@register_adapter('classify')
@register_renderer(ClassifyRenderer)
class ClassifyAdapter(ResourceAdapter):
    """Provenance classification (first_party/test/vendor/minified) for
    every file in a directory, independent of any ranking or selection
    (BACK-1233) -- the full-population counterpart to overview://'s/
    hotspots://'s/pack://'s ranked-subset provenance tags (BACK-1195)."""

    HELP_CLUSTER = 'Code Analysis'
    LEGACY_INIT = False  # canonical (resource, query) signature — BACK-907
    # BACK-1379: _classify_directory already calls find_analyzable_files(), which
    # defaults respect_gitignore=True -- but nothing here ever passed False, so
    # --no-gitignore was silently swallowed (confirmed live: identical file count
    # with/without the flag) even though the underlying gitignore-aware walker
    # (shared with stats:// and overview://) already supports disabling it.
    CLI_QUERY_FLAGS = {'respect_gitignore': 'respect_gitignore=false'}

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
            'query_params': {
                'respect_gitignore': {
                    'type': 'boolean',
                    'description': 'Skip gitignored files (default true). Same as the CLI --no-gitignore (which sets this to false)',
                    'examples': ['classify://src?respect_gitignore=false'],
                },
            },
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
        return provenance_report(path, respect_gitignore=respect_gitignore_param(self.query_params))
