"""D005: Cross-file hardcoded literal cluster detector.

Detects the same hardcoded list/set/tuple literal appearing in multiple files —
the duplication pattern M104 (per-file) structurally cannot see.

Example violation:
    # analyzer_a.py
    SKIP_DIRS = {'.git', 'node_modules', 'venv', '__pycache__', 'dist'}

    # analyzer_b.py
    SKIP_DIRS = {'.git', 'node_modules', 'venv', '__pycache__', 'dist'}  # D005

Example fix:
    # defaults.py
    SKIP_DIRECTORIES = {'.git', 'node_modules', 'venv', '__pycache__', 'dist'}

    # analyzer_a.py and analyzer_b.py
    from defaults import SKIP_DIRECTORIES

Uses the same scan-all-files-once-per-project cache strategy as I002 so that
every file in a cluster is reported, not just the N-th one seen.
"""

import ast
import hashlib
import logging
import os
from dataclasses import asdict
from ...core import disk_cache
from ...utils.request_cache import register_validated_cache
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin
from ...utils.pyparse import parse_python, statement_index
from ...utils.query_control import ScanBudget
from ...utils.path_utils import EVIDENCE, _walk_code_files, cross_file_scan_root, scan_roots, to_posix

logger = logging.getLogger(__name__)

class LiteralIndex(dict):
    """The existing literal mapping plus its picklable source-scan accounting."""

    def __init__(self, budget: ScanBudget, admitted: int, capped: bool = False):
        super().__init__()
        self.scan_budget = {**asdict(budget.accounting(admitted, capped)),
                            'limit': budget.limit, 'analyzed_files': 0,
                            'failed_files': 0, 'skipped': capped}
        self.disclosures: List[str] = []


# ── Module-level cache ────────────────────────────────────────────────────────
# project_root → {canonical_key → [(abs_file_path, lineno, var_name), ...]}
_project_index: Dict[Path, Dict[str, List[Tuple[str, int, str]]]] = {}

# BACK-1051: project_root → one-line reason, set whenever _build_index bailed
# on the file-count ceiling instead of scanning. Mirrors I002's
# ImportGraph.scan_skipped_reason -- carried alongside the (empty) index so a
# directory-level check/review run can disclose the skip instead of letting
# an empty index present itself as "no duplicate literal clusters found".
_project_skip_reasons: Dict[Path, str] = {}

# ── Constants ─────────────────────────────────────────────────────────────────
_COLLECTION_BUILTINS = {'frozenset', 'set', 'tuple', 'list'}

# Name substrings that indicate stable / intentional lists — skip them.
_STABLE_NAME_PATTERNS = {
    '__all__', 'output_format', 'format', 'test_', 'mock_', 'fixture',
    'example', 'sample',
}

# Safety ceiling: cross-file detection scans every .py under the project root
# on first check, so a huge tree is skipped (with a logged warning) rather than
# stalling an interactive --check. Override with REVEAL_D005_MAX_FILES for large
# monorepos that genuinely want the scan. Mirrors I002's REVEAL_I002_MAX_FILES.
_DEFAULT_MAX_PROJECT_FILES = 5000


def _max_project_files() -> int:
    """Read the scan ceiling, honoring REVEAL_D005_MAX_FILES."""
    raw = os.environ.get('REVEAL_D005_MAX_FILES')
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            logger.debug("Invalid REVEAL_D005_MAX_FILES=%r, using default", raw)
    return _DEFAULT_MAX_PROJECT_FILES


# ── Helpers (module-level, no self) ──────────────────────────────────────────

def _find_project_root(path: Path) -> Optional[Path]:
    """Nearest project root above *path* via the shared, ceiling-bounded
    resolver (BACK-612): ``.reveal.yaml root:true`` → package marker → VCS root.
    Falls back to the file's own directory when nothing matches before the
    hard ceiling, and is ``None`` when that directory is the OS temp dir,
    $HOME or a filesystem root (:func:`cross_file_scan_root`). Honors
    ``root:true`` and ``.git`` and the ``__init__.py`` guard — so D005's
    duplicate scan is scoped to the same project boundary depends:// uses."""
    return cross_file_scan_root(path)


def _canonical_key(values: frozenset) -> str:
    """Stable, order-independent string key for a frozenset of scalar values."""
    joined = '|'.join(sorted(str(v) for v in values))
    return hashlib.sha256(joined.encode()).hexdigest()


def _resolve_collection(value: ast.AST) -> Optional[ast.AST]:
    """Return the inner collection node (with .elts) or None."""
    if isinstance(value, (ast.List, ast.Set, ast.Tuple)):
        return value
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in _COLLECTION_BUILTINS
        and len(value.args) == 1
        and isinstance(value.args[0], (ast.List, ast.Set, ast.Tuple))
    ):
        return value.args[0]
    return None


def _extract_constants(node: ast.AST, min_size: int) -> Optional[frozenset]:
    """Extract string/number scalar constants from a collection node.

    Returns None if the node has too few qualifying constants.
    """
    if not hasattr(node, 'elts'):
        return None
    values = []
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, (str, int, float)):
            values.append(elt.value)
    if len(values) < min_size:
        return None
    return frozenset(values)


def _is_stable_name(name: str) -> bool:
    name_lower = name.lower()
    return any(p in name_lower for p in _STABLE_NAME_PATTERNS)


def _clear_index() -> None:
    """Clear the project index cache (for tests)."""
    _project_index.clear()
    _project_skip_reasons.clear()


def get_scan_disclosures(files: Optional[List[Path]] = None) -> List[str]:
    """BACK-1051: one-line skip reasons for every project root whose D005
    cross-file scan was skipped by the file-count ceiling. Mirrors
    I002.get_scan_disclosures()."""
    roots = scan_roots(files, _find_project_root) if files is not None else None
    details = [message for root, index in _project_index.items()
               if roots is None or root in roots
               for message in _index_disclosures(root, index)]
    skipped = [message for root, message in _project_skip_reasons.items()
               if roots is None or root in roots]
    return list(dict.fromkeys([*skipped, *details]))


def _index_disclosures(root: Path, index: dict) -> List[str]:
    """Keep complete numeric accounting and bound the per-file diagnostic display."""
    from ...rendering.base import capped_section
    messages = sorted(getattr(index, 'disclosures', []))
    failed = getattr(index, 'scan_budget', {}).get('failed_files', 0)
    if not failed:
        return messages
    return [f'D005: {failed} file(s) under {root} were not analyzed; cross-file results may be incomplete',
            *capped_section(messages, 5, str, indent='D005: ')]


def get_scan_budgets(files: List[Path]) -> List[Dict[str, Any]]:
    """Accounting follows the same cached artifact that workers receive."""
    return [{'rule': 'D005', 'root': root, **index.scan_budget}
            for root, index in _project_index.items() if isinstance(index, LiteralIndex)
            and any(path.resolve().is_relative_to(root) for path in files)]


# ── Rule ──────────────────────────────────────────────────────────────────────

class D005(BaseRule, ASTParsingMixin):
    """Detect hardcoded literal clusters duplicated across multiple files.

    Flags any list/set/tuple literal of MIN_LITERAL_SIZE+ items that appears
    in MIN_CLUSTER_FILES+ distinct files with identical values (order-independent).
    """

    code = "D005"
    message = "Hardcoded literal cluster duplicated across files"
    category = RulePrefix.D
    severity = Severity.MEDIUM
    file_patterns = ['.py']

    # Minimum items in the literal to be considered (small lists are often deliberate)
    MIN_LITERAL_SIZE = 5
    # Minimum number of *distinct files* before flagging
    MIN_CLUSTER_FILES = 3

    # ── Public helpers (also used by _build_index) ────────────────────────────

    def extract_file_literals(
        self, file_path: str, content: str
    ) -> List[Tuple[str, int, str, frozenset]]:
        """Extract qualifying literal cluster entries from one file.

        Returns list of (canonical_key, lineno, var_name, value_frozenset).
        """
        try:
            tree = parse_python(content)
        except SyntaxError:
            return []

        return self._literals_from_tree(tree)

    def _literals_from_tree(self, tree: ast.Module) -> List[Tuple[str, int, str, frozenset]]:
        results = []
        seen_keys: set = set()  # deduplicate within file

        for node in statement_index(tree)[0]:
            if not isinstance(node, ast.Assign):
                continue
            col_node = _resolve_collection(node.value)
            if col_node is None:
                continue
            values = _extract_constants(col_node, self.MIN_LITERAL_SIZE)
            if values is None:
                continue
            key = _canonical_key(values)
            if key in seen_keys:
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if _is_stable_name(target.id):
                    continue
                seen_keys.add(key)
                results.append((key, node.lineno, target.id, values))
                break  # one var_name per assignment

        return results

    # ── Core check ────────────────────────────────────────────────────────────

    def check(
        self,
        file_path: str,
        structure: Optional[Dict[str, Any]],
        content: str,
    ) -> List[Detection]:
        path = Path(file_path).resolve()
        project_root = _find_project_root(path)
        if project_root is None:
            logger.debug("D005: no cross-file scan for standalone file under %s", path.parent)
            return []

        if project_root not in _project_index:
            _project_index[project_root] = _build_index(project_root, self)

        index = _project_index[project_root]
        file_str = str(path)
        detections = []

        for key, occurrences in index.items():
            distinct_files = {fp for fp, _, _ in occurrences}
            if len(distinct_files) < self.MIN_CLUSTER_FILES:
                continue
            # Report only occurrences in THIS file
            for fp, line, var_name in occurrences:
                if fp != file_str:
                    continue
                other_files = sorted(distinct_files - {file_str})
                n_total = len(distinct_files)
                sample = [Path(f).name for f in other_files[:3]]
                ellipsis = '...' if len(other_files) > 3 else ''
                detections.append(self.create_detection(
                    file_path=file_path,
                    line=line,
                    message=f"'{var_name}' duplicated across {n_total} files — extract to a shared constant",
                    suggestion="Move to a shared constants module and import from there",
                    context=f"Also in: {', '.join(sample)}{ellipsis}",
                ))

        return detections


# ── Index builder ─────────────────────────────────────────────────────────────

_LITERALS_NAMESPACE = 'd005_literals'
_LITERALS_CACHE_MAX_FILES = 100_000


def _file_literals(py_file: Path, rule: D005) -> List[Tuple[str, int, str, frozenset]]:
    """One file's literal clusters; the disk cache answers for an unchanged file (BACK-1872).

    The extraction reads only that file, so the key is the file's identity (path, mtime_ns,
    size) plus the size threshold the extraction depends on; the cache's build fingerprint
    covers a change to this code. A file that fails to read or parse raises and is never
    cached, so its disclosure is re-derived on every run.
    """
    path_str = os.path.abspath(str(py_file))
    stat = os.stat(path_str)
    key = hashlib.sha256(
        f'{path_str}\0{stat.st_mtime_ns}\0{stat.st_size}\0{rule.MIN_LITERAL_SIZE}'.encode('utf-8', 'replace')
    ).hexdigest()
    cached = disk_cache.get(_LITERALS_NAMESPACE, key)
    if isinstance(cached, list):
        return cached
    content = py_file.read_text(encoding='utf-8', errors='ignore')
    literals = rule._literals_from_tree(parse_python(content))
    disk_cache.put(_LITERALS_NAMESPACE, key, literals, max_entries=_LITERALS_CACHE_MAX_FILES)
    return literals


def _build_index(
    project_root: Path, rule: D005
) -> Dict[str, List[Tuple[str, int, str]]]:
    """Scan all .py files under project_root and build the cross-file literal index.

    Collects paths lazily and aborts as soon as the file count crosses the
    ceiling — a huge tree (e.g. a marker-less parent that aggregates many
    projects) is skipped without materializing the full list or parsing a
    single file, so an interactive --check never stalls.
    """
    budget = ScanBudget(_max_project_files())
    ceiling = budget.limit
    _project_skip_reasons.pop(project_root, None)
    py_files: List[Path] = []
    # The evidence walk (BACK-1578): noise, gitignored and REVEAL_IGNORE'd files are not
    # the project's literals, --exclude narrows the report and not the index. It judges
    # paths relative to the root: the old filter tested every component of the absolute
    # path, so a project under ~/.config/ or ~/.cache/ had every file skipped. os.walk
    # skips a directory that vanishes mid-scan (a shared temp dir) instead of raising.
    for p in _walk_code_files(project_root, purpose=EVIDENCE):
        if p.suffix != '.py':
            continue
        py_files.append(p)
        if ceiling is not None and len(py_files) > ceiling:
            reason = (
                f"D005: project root {project_root} exceeds {ceiling} .py files; "
                "skipping cross-file scan (set REVEAL_D005_MAX_FILES to raise "
                "the ceiling)"
            )
            logger.warning(reason)
            _project_skip_reasons[project_root] = reason
            index = LiteralIndex(budget, ceiling, capped=True)
            index.disclosures.append(reason)
            return index

    index = LiteralIndex(budget, len(py_files))

    for py_file in py_files:
        try:
            literals = _file_literals(py_file, rule)
        except (OSError, ValueError, SyntaxError) as exc:
            index.scan_budget['failed_files'] += 1
            index.disclosures.append(f'D005: {to_posix(py_file)} was not analyzed ({type(exc).__name__}); cross-file results may be incomplete')
            continue
        index.scan_budget['analyzed_files'] += 1
        for key, line, var_name, _ in literals:
            index.setdefault(key, []).append((str(py_file), line, var_name))

    return index


def _evict_root(root: Path) -> None:
    _project_index.pop(root, None)
    _project_skip_reasons.pop(root, None)


register_validated_cache(__name__, _project_index, _evict_root)
