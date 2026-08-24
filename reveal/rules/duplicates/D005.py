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
from pathlib import Path
from typing import Dict, Iterator, List, Any, Optional, Tuple

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin
from ...utils.path_utils import is_skippable_dir, resolve_project_root

logger = logging.getLogger(__name__)

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

def _find_project_root(path: Path) -> Path:
    """Nearest project root above *path* via the shared, ceiling-bounded
    resolver (BACK-612): ``.reveal.yaml root:true`` → package marker → VCS root.
    Falls back to the file's own directory when nothing matches before the
    hard ceiling. Now honors ``root:true`` and ``.git`` (which the old flat
    5-marker climb ignored) and the ``__init__.py`` guard — so D005's
    duplicate scan is scoped to the same project boundary depends:// uses."""
    root = resolve_project_root(path)
    return root if root is not None else path.parent


def _canonical_key(values: frozenset) -> str:
    """Stable, order-independent string key for a frozenset of scalar values."""
    joined = '|'.join(sorted(str(v) for v in values))
    return hashlib.sha256(joined.encode()).hexdigest()


def _should_skip_path(path: Path) -> bool:
    """True if any path component is a skip-directory or hidden directory.

    BACK-552: ambiguous names (env/venv/build/dist) checked against actual
    directory content via is_skippable_dir(), not bare name alone.
    """
    accumulated = Path(path.anchor) if path.is_absolute() else Path()
    for part in path.parts:
        if part == path.anchor:
            continue
        if (part.startswith('.') and part != '.') or is_skippable_dir(accumulated, part):
            return True
        accumulated = accumulated / part
    return False


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


def get_scan_disclosures() -> List[str]:
    """BACK-1051: one-line skip reasons for every project root whose D005
    cross-file scan was skipped by the file-count ceiling. Mirrors
    I002.get_scan_disclosures()."""
    return list(_project_skip_reasons.values())


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
            tree = ast.parse(content)
        except SyntaxError:
            return []

        results = []
        seen_keys: set = set()  # deduplicate within file

        for node in ast.walk(tree):
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

def _iter_py_files(root: Path) -> Iterator[Path]:
    """Yield .py files under root, tolerating a directory that vanishes mid-scan.

    ``Path.rglob`` raises ``FileNotFoundError`` (Windows: WinError 3) if a
    subdirectory it queued for traversal is deleted between when its parent
    was listed and when rglob descends into it -- a real TOCTOU race, not a
    hypothetical one: when ``_find_project_root`` falls back to a file's own
    parent (no ``.reveal.yaml``/VCS marker found -- e.g. a throwaway file
    outside any project), that parent can be a shared, high-churn directory
    like the OS temp dir, where sibling entries are actively created/deleted
    by unrelated processes. Manual stack-based walk so one vanished directory
    is skipped instead of aborting the whole scan (mirrors the per-file
    ``except OSError: continue`` a few lines below, for the same reason).
    """
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            if is_dir:
                stack.append(Path(entry.path))
            elif entry.name.endswith('.py'):
                yield Path(entry.path)


def _build_index(
    project_root: Path, rule: D005
) -> Dict[str, List[Tuple[str, int, str]]]:
    """Scan all .py files under project_root and build the cross-file literal index.

    Collects paths lazily and aborts as soon as the file count crosses the
    ceiling — a huge tree (e.g. a marker-less parent that aggregates many
    projects) is skipped without materializing the full list or parsing a
    single file, so an interactive --check never stalls.
    """
    ceiling = _max_project_files()
    py_files: List[Path] = []
    for p in _iter_py_files(project_root):
        if _should_skip_path(p):
            continue
        py_files.append(p)
        if len(py_files) > ceiling:
            reason = (
                f"D005: project root {project_root} exceeds {ceiling} .py files; "
                "skipping cross-file scan (set REVEAL_D005_MAX_FILES to raise "
                "the ceiling)"
            )
            logger.warning(reason)
            _project_skip_reasons[project_root] = reason
            return {}

    index: Dict[str, List[Tuple[str, int, str]]] = {}

    for py_file in py_files:
        try:
            content = py_file.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for key, line, var_name, _ in rule.extract_file_literals(str(py_file), content):
            index.setdefault(key, []).append((str(py_file), line, var_name))

    return index
