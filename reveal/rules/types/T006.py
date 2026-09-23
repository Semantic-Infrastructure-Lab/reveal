"""T006: a param typed as an untyped dict reads the keys of an existing TypedDict.

Fires when a function parameter annotated as an untyped dict -- `dict`,
`Dict[...]`, `Mapping[...]`, `Any`, a dict type alias, or Optional/Union of
those -- reads keys an existing TypedDict declares, covering most of what the
function reads. The TypedDict may live anywhere in the project, not just the
same module: the usual case is a shared record type in one module
(`types.py`) that readers elsewhere never adopted. A same-module TypedDict
needs 3 shared keys; one from another module needs 4, since generic keys
(file/line/name) recur across unrelated record types.

Only annotated params fire. Unannotated params are T005's concern, and loop
variables / locals have no line-level fix (their type comes from whatever
they iterate) -- `ast://<path>?show=dict-schemas` reports those.

Analysis lives in reveal/analyzers/_python_dict_usage.py, shared with
`ast://?show=dict-heatmap` / `?show=dict-schemas`.
"""

import ast
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin
from ...utils.pyparse import parse_python
from ...analyzers._python_dict_usage import (
    SCHEMA_MIN_SHARED_KEYS,
    best_typeddict_match,
    build_context,
    collect_typeddict_definitions,
    function_dict_usages,
    has_untyped_dict_param,
    iter_python_files,
    resolve_typeddicts,
)
from ...utils.path_utils import resolve_project_root

logger = logging.getLogger(__name__)

# project_root -> {'typeddicts': [TypedDict record, ...], 'dict_aliases': frozenset}
_project_index: Dict[Path, Dict[str, Any]] = {}
# BACK-1051 pattern: project_root -> why its cross-module scan was skipped
_project_skip_reasons: Dict[Path, str] = {}

_DEFAULT_MAX_PROJECT_FILES = 5000
_REMOTE_MIN_SHARED_KEYS = 4
_EMPTY_FACTS: Dict[str, Any] = {'typeddicts': [], 'dict_aliases': frozenset()}

# Only files that can define a TypedDict or a dict type alias are parsed when
# indexing a project; everything else costs one read and one regex search.
_DEFINES_TYPE_FACTS = re.compile(
    r'TypedDict'
    r'|^\w+\s*(?::\s*TypeAlias\s*)?=\s*(?:typing\.)?'
    r'(?:Dict|dict|Mapping|MutableMapping|DefaultDict|OrderedDict|Optional|Union)\b'
    r'|^type\s+\w+',
    re.MULTILINE,
)


class T006(BaseRule, ASTParsingMixin):
    """Suggest an existing TypedDict for a param annotated as an untyped dict.

    Fires when a param annotated dict / Dict[...] / Mapping / Any / a dict alias
    reads keys (d['k'], d.get('k'), 'k' in d) that a TypedDict anywhere in the
    project declares: 3+ shared keys if it is in the same module, 4+ otherwise,
    covering 60% of what the function reads. Loop vars and locals are reported
    by ast://<path>?show=dict-schemas instead. Project scan capped by
    REVEAL_T006_MAX_FILES (default 5000).
    """

    code = "T006"
    message = "Function uses bare dict but a matching TypedDict is available"
    category = RulePrefix.T
    severity = Severity.LOW
    file_patterns = ['.py']
    version = "2.0.0"

    def check(
        self,
        file_path: str,
        structure: Optional[Dict[str, Any]],
        content: str,
    ) -> List[Detection]:
        tree, detections = self._parse_python_or_skip(content, file_path)
        if tree is None:
            return detections

        facts = _project_facts(file_path)
        visible = _visible_typeddicts(tree, file_path, facts['typeddicts'])
        if not visible:
            return detections
        local = [td for td in visible if td['file'] == file_path]
        remote = [td for td in visible if td['file'] != file_path]

        ctx = build_context([tree], known_aliases=facts['dict_aliases'])
        for node in self._ast_walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not has_untyped_dict_param(node, ctx.dict_aliases):
                continue
            for usage in function_dict_usages(node, file_path, ctx):
                detection = self._detect(usage, local, remote, file_path)
                if detection is not None:
                    detections.append(detection)
        return detections

    def _detect(
        self,
        usage: Dict[str, Any],
        local: List[Dict[str, Any]],
        remote: List[Dict[str, Any]],
        file_path: str,
    ) -> Optional[Detection]:
        if usage['source'] != 'annotated_param':
            return None
        keys = set(usage['keys'])
        if len(keys) < SCHEMA_MIN_SHARED_KEYS:
            return None
        match = _best_match(keys, local, remote)
        if match is None:
            return None

        td, matched = match
        name, annotation = usage['param'], usage['annotation']
        where = '' if td['file'] == file_path else f" (defined at {_display(td)})"
        undeclared = sorted(keys - matched)
        context = f"Keys accessed: {', '.join(sorted(matched)[:6])}"
        if undeclared:
            context += f"; not declared on {td['name']}: {', '.join(undeclared[:6])}"
        return self.create_detection(
            file_path=file_path,
            line=usage['line'],
            message=(
                f"{usage['function']}: param '{name}: {annotation}' — "
                f"TypedDict '{td['name']}' covers {len(matched)}/{len(keys)} accessed keys"
            ),
            suggestion=f"Replace '{annotation}' with '{td['name']}' for param '{name}'{where}",
            context=context,
        )


# ─────────────────────────── TypedDict visibility ────────────────────────────

def _best_match(
    keys: set,
    local: List[Dict[str, Any]],
    remote: List[Dict[str, Any]],
) -> Optional[tuple]:
    """A same-module TypedDict needs SCHEMA_MIN_SHARED_KEYS shared keys; one
    from another module needs _REMOTE_MIN_SHARED_KEYS, because nothing ties
    the reader to it but the keys, and generic keys (file/line/name) recur
    across unrelated record types. On equal evidence the local one wins."""
    local_match = best_typeddict_match(keys, local)
    remote_match = best_typeddict_match(keys, remote, min_shared=_REMOTE_MIN_SHARED_KEYS)
    if remote_match and (not local_match or len(remote_match[1]) > len(local_match[1])):
        return remote_match
    return local_match


def _visible_typeddicts(
    tree: ast.Module,
    file_path: str,
    project_typeddicts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """This module's TypedDicts first (so they win ties and same-name
    shadowing), then the project's -- merged before resolution so a local
    subclass of a project TypedDict inherits its fields. The project index's
    copy of this module is dropped: the in-memory content is authoritative,
    and its records keep `file == file_path` so callers can tell local ones
    apart by plain comparison."""
    raw: Dict[str, List[Dict[str, Any]]] = {}
    collect_typeddict_definitions(tree, file_path, raw)
    here = Path(file_path).resolve()
    for td in project_typeddicts:
        if Path(td['file']) != here:
            raw.setdefault(td['name'], []).append({
                'name': td['name'], 'file': td['file'], 'line': td['line'],
                'bases': [], 'own_fields': td['fields'], 'functional': True,
            })
    return resolve_typeddicts(raw)


def _display(td: Dict[str, Any]) -> str:
    try:
        path = os.path.relpath(td['file'])
    except ValueError:  # different drive on Windows
        path = td['file']
    return f"{path}:{td['line']}"


# ─────────────────────────── project index ───────────────────────────────────

def _project_facts(file_path: str) -> Dict[str, Any]:
    """TypedDicts and dict aliases defined anywhere in file_path's project.

    Only for a file that exists on disk: in-memory content under a phantom
    path (stdin, tests) has no project, and indexing whatever directory the
    process runs in would attribute unrelated TypedDicts to it.
    """
    path = Path(file_path)
    if not path.is_file():
        return _EMPTY_FACTS
    root = _find_project_root(path.resolve())
    if root not in _project_index:
        _project_index[root] = _build_index(root)
    return _project_index[root]


def _find_project_root(path: Path) -> Path:
    root = resolve_project_root(path)
    return root if root is not None else path.parent


def _max_project_files() -> int:
    raw = os.environ.get('REVEAL_T006_MAX_FILES')
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            logger.debug("Invalid REVEAL_T006_MAX_FILES=%r, using default", raw)
    return _DEFAULT_MAX_PROJECT_FILES


def _build_index(project_root: Path) -> Dict[str, Any]:
    """Scan project_root once for TypedDict and dict-alias definitions.

    Aborts past the file-count ceiling -- a huge marker-less parent must not
    stall an interactive check -- and records why, so the run can say
    cross-module matching was skipped instead of implying none exists.
    """
    ceiling = _max_project_files()
    files = []
    for file_path in iter_python_files(str(project_root)):
        files.append(file_path)
        if len(files) > ceiling:
            reason = (
                f"T006: project root {project_root} exceeds {ceiling} .py files; "
                "matching TypedDicts from the same module only "
                "(set REVEAL_T006_MAX_FILES to raise the ceiling)"
            )
            logger.warning(reason)
            _project_skip_reasons[project_root] = reason
            return _EMPTY_FACTS

    raw: Dict[str, List[Dict[str, Any]]] = {}
    trees = []
    for file_path in files:
        try:
            text = Path(file_path).read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        if not _DEFINES_TYPE_FACTS.search(text):
            continue
        try:
            tree = parse_python(text, str(file_path))
        except (SyntaxError, ValueError):
            continue
        trees.append(tree)
        collect_typeddict_definitions(tree, file_path, raw)

    aliases: FrozenSet[str] = build_context(trees).dict_aliases
    return {'typeddicts': resolve_typeddicts(raw), 'dict_aliases': aliases}


def get_scan_disclosures() -> List[str]:
    """One-line reasons for every project whose cross-module TypedDict scan
    was skipped by the file-count ceiling. Mirrors D005/I002."""
    return list(_project_skip_reasons.values())


def _clear_index() -> None:
    """Clear the project index cache (for tests)."""
    _project_index.clear()
    _project_skip_reasons.clear()
