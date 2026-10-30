"""Provenance tag for every file in a directory's full, unranked population (BACK-1233).

BACK-1195 introduced ranked provenance tagging; hotspots:// and pack://
retain that selection-based output, but a DD consumer asking "what fraction of this
codebase is first-party" needs the tag over the FULL file population,
independent of any adapter's own ranking or selection -- structurally
uncomputable from either ranked view (each only tags whatever subset it
already selects for its own purpose). This reuses BACK-1195's
classify_path_provenance() and the stats walker find_analyzable_files()
rather than building a new classifier or a new directory walk.

The one owner of the classification and its report (metrics://?view=provenance and the retired
classify:// answer from it; stats/renderer.py renders it).
No file is analyzed and no rule runs: paths, plus at most the first few lines of
a file the path did not already classify.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

from ...utils.path_utils import (
    classify_path_provenance,
    is_vendor_dir,
    looks_vendored_by_banner,
    failure_of,
)
from ...utils.results import ResultBuilder
from .analysis import find_analyzable_files, get_file_display_path
from ...reveal_types import PathFailure

PROVENANCE_RESULT_TYPE = 'classify_report'

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


def apply_locale_fanout(rows: List[Dict[str, Any]]) -> None:
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
        # BACK-1258: check every ancestor, not just the immediate parent.
        # Rails and Django both nest locale files below the i18n root
        # (config/locales/<engine>/<area>/en.yml), so an immediate-parent test
        # sees 'admin'/'common'/'routes' and misses the exemption entirely --
        # measured on camaleon-cms, 56 of the project's own translation files
        # (74% of every vendor verdict on that repo) were labelled vendor.
        if (
            any(p.lower() in _FIRST_PARTY_I18N_DIR_NAMES for p in parent_parts)
            and not any(is_vendor_dir(p) for p in parent_parts)
        ):
            continue
        for row in group_rows:
            if row['provenance'] == 'first_party':
                row['provenance'] = 'vendor'


def classify_directory(directory: Path, respect_gitignore: Optional[bool] = None, *,
                       on_error: Optional[Callable[[OSError], None]] = None
                       ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Return (rows, excluded_by_extension), reporting enumeration loss via on_error.

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
    for file_path in find_analyzable_files(
            directory, respect_gitignore=respect_gitignore, excluded_by_extension=excluded_by_extension,
            on_error=on_error):
        rel = Path(get_file_display_path(file_path, directory))
        provenance = classify_path_provenance(rel.parts[:-1], rel.name)
        if provenance is None and looks_vendored_by_banner(file_path):
            provenance = 'vendor'
        rows.append({
            'file': rel.as_posix(),
            'provenance': provenance or 'first_party',
        })
    apply_locale_fanout(rows)
    return rows, excluded_by_extension


def provenance_report(path: Path, respect_gitignore: Optional[bool] = None) -> Dict[str, Any]:
    """The full-population report for *path* (its parent directory when *path* is a file)."""
    from ..ast.analysis import traversal_failed_warning

    directory = path if path.is_dir() else path.parent
    failures: List[PathFailure] = []

    def on_error(error: OSError) -> None:
        failures.append(failure_of(error))

    rows, excluded_by_extension = classify_directory(
        directory, respect_gitignore=respect_gitignore, on_error=on_error)
    warning = traversal_failed_warning(failures, directory)

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

    return cast(Dict[str, Any], ResultBuilder.create(
        result_type=PROVENANCE_RESULT_TYPE,
        source=str(path),
        data=data,
        warnings=[warning] if warning else None,
    ))

