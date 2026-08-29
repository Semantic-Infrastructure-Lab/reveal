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

from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import ResourceAdapter, register_adapter, register_renderer
from .stats.analysis import find_analyzable_files, get_file_display_path
from ..utils import print_json_result
from ..utils.path_utils import classify_path_provenance
from ..utils.query import parse_query_params
from ..utils.results import ResultBuilder
from ..utils.validation import require_path_exists


def _classify_directory(directory: Path) -> List[Dict[str, Any]]:
    rows = []
    for file_path in find_analyzable_files(directory):
        rel = Path(get_file_display_path(file_path, directory))
        provenance = classify_path_provenance(rel.parts[:-1], rel.name)
        rows.append({
            'file': rel.as_posix(),
            'provenance': provenance or 'first_party',
        })
    return rows


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
            'description': 'Provenance tag (first_party/test/vendor/minified) for every file in a directory, over the full unranked population.',
            'syntax': 'classify://<dir>',
            'examples': [
                {'uri': 'classify://src', 'description': 'Provenance for every analyzable file under src/'},
            ],
            'features': [
                'One row per file — not a ranked/capped subset like overview://, hotspots://, pack://',
                'Path-only classifier: no file content is read',
                'summary.by_provenance gives a first-party-vs-noise fraction for the whole target',
            ],
            'notes': [
                "Content-based generated-file detection (checks.py's _is_generated_file) is not folded in — path-only classification only.",
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
            'description': 'Provenance classification for every file in a directory, full population',
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
                'Path-only classification (directory/filename conventions) — no file content is read.',
            ],
        }

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        path = Path(self.path)
        require_path_exists(path)

        directory = path if path.is_dir() else path.parent
        rows = _classify_directory(directory)

        by_provenance: Dict[str, int] = {}
        for row in rows:
            by_provenance[row['provenance']] = by_provenance.get(row['provenance'], 0) + 1

        data = {
            'files': rows,
            'summary': {
                'total': len(rows),
                'by_provenance': by_provenance,
            },
        }

        return ResultBuilder.create(
            result_type='classify_report',
            source=str(path),
            data=data,
        )
