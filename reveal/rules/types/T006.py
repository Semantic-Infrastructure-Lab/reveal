"""T006: TypedDict available but function uses bare dict.

When a TypedDict is defined (or imported and re-exported) in the same module and
a function parameter is annotated as bare `dict` or `Dict[...]`, T006 checks
whether the keys accessed on that parameter match ≥3 fields of the TypedDict.
If so, it suggests replacing `dict` with the more specific TypedDict name.

This fires *before* annotation exists — it's a nudge, not an enforcement.
Fully unannotated parameters (no `dict` annotation at all) are skipped;
T005 handles annotation coverage separately.
"""

import ast
from typing import Dict, List, Optional, Set, Any

from ..base import BaseRule, Detection, RulePrefix, Severity
from ..base_mixins import ASTParsingMixin

_BARE_DICT_NAMES = frozenset({'dict', 'Dict'})
_MIN_KEY_MATCH = 3


class T006(BaseRule, ASTParsingMixin):
    """Suggest TypedDict when bare dict annotation + matching TypedDict exists."""

    code = "T006"
    message = "Function uses bare dict but a matching TypedDict is available"
    category = RulePrefix.T
    severity = Severity.LOW
    file_patterns = ['.py']
    version = "1.0.0"

    def check(
        self,
        file_path: str,
        structure: Optional[Dict[str, Any]],
        content: str,
    ) -> List[Detection]:
        tree, detections = self._parse_python_or_skip(content, file_path)
        if tree is None:
            return detections

        typeddicts = _collect_typeddicts(tree)
        if not typeddicts:
            return detections

        for node in self._ast_walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _check_function(node, typeddicts, file_path, detections, self)

        return detections


# ─────────────────────────── TypedDict collection ────────────────────────────

def _collect_typeddicts(tree: ast.AST) -> Dict[str, Set[str]]:
    """Return {TypedDict_name: {field, ...}} for all TypedDicts in module scope."""
    result: Dict[str, Set[str]] = {}

    for node in ast.walk(tree):
        # Class-based: class Trade(TypedDict): symbol: str; pnl: float
        if isinstance(node, ast.ClassDef) and _has_typed_dict_base(node):
            fields = _extract_class_fields(node)
            if fields:
                result[node.name] = fields

        # Functional: Trade = TypedDict('Trade', symbol=str, pnl=float)
        # or:         Trade = TypedDict('Trade', {'symbol': str, 'pnl': float})
        elif isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                fields = _extract_functional_typeddict(node.value)
                if fields:
                    result[name] = fields

    return result


def _has_typed_dict_base(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == 'TypedDict':
            return True
        if isinstance(base, ast.Attribute) and base.attr == 'TypedDict':
            return True
    return False


def _extract_class_fields(node: ast.ClassDef) -> Set[str]:
    fields: Set[str] = set()
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            fields.add(stmt.target.id)
    return fields


def _extract_functional_typeddict(value: ast.expr) -> Optional[Set[str]]:
    if not (isinstance(value, ast.Call)):
        return None
    func = value.func
    if not (
        (isinstance(func, ast.Name) and func.id == 'TypedDict') or
        (isinstance(func, ast.Attribute) and func.attr == 'TypedDict')
    ):
        return None

    fields: Set[str] = set()

    # keyword form: TypedDict('X', symbol=str, pnl=float)
    for kw in value.keywords:
        if kw.arg:
            fields.add(kw.arg)

    # dict form: TypedDict('X', {'symbol': str, 'pnl': float})
    if len(value.args) >= 2 and isinstance(value.args[1], ast.Dict):
        for key in value.args[1].keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                fields.add(key.value)

    return fields if fields else None


# ─────────────────────────── function checking ───────────────────────────────

def _check_function(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    typeddicts: Dict[str, Set[str]],
    file_path: str,
    detections: List[Detection],
    rule: 'T006',
) -> None:
    args = func_node.args
    all_args = (
        args.posonlyargs + args.args + args.kwonlyargs
        + ([args.vararg] if args.vararg else [])
        + ([args.kwarg] if args.kwarg else [])
    )
    # Only check params explicitly annotated as bare dict / Dict
    bare_dict_params = [
        a for a in all_args
        if a.annotation is not None and _is_bare_dict(a.annotation)
    ]
    if not bare_dict_params:
        return

    for param in bare_dict_params:
        keys_accessed = _collect_subscript_keys(func_node, param.arg)
        if len(keys_accessed) < _MIN_KEY_MATCH:
            continue

        best_match = _best_typeddict_match(keys_accessed, typeddicts)
        if best_match is None:
            continue

        td_name, matched_keys = best_match
        overlap = len(matched_keys)
        detections.append(rule.create_detection(
            file_path=file_path,
            line=func_node.lineno,
            message=(
                f"{func_node.name}: param '{param.arg}: dict' — "
                f"TypedDict '{td_name}' covers {overlap}/{len(keys_accessed)} "
                f"accessed keys"
            ),
            suggestion=f"Replace 'dict' with '{td_name}' for param '{param.arg}'",
            context=f"Keys accessed: {', '.join(sorted(matched_keys)[:6])}",
        ))


def _is_bare_dict(annotation: ast.expr) -> bool:
    if isinstance(annotation, ast.Name):
        return annotation.id in _BARE_DICT_NAMES
    if isinstance(annotation, ast.Attribute):
        return annotation.attr in _BARE_DICT_NAMES
    # Dict[K, V] — subscripted form
    if isinstance(annotation, ast.Subscript):
        return _is_bare_dict(annotation.value)
    return False


def _collect_subscript_keys(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    param_name: str,
) -> Set[str]:
    """Collect string keys accessed via param_name['key'] in the function body."""
    keys: Set[str] = set()
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Subscript):
            continue
        target = node.value
        if not (isinstance(target, ast.Name) and target.id == param_name):
            continue
        idx = node.slice
        # Python 3.9+: slice is the index directly; earlier: ast.Index wrapper
        if isinstance(idx, ast.Index):
            idx = idx.value  # type: ignore[attr-defined]
        if isinstance(idx, ast.Constant) and isinstance(idx.value, str):
            keys.add(idx.value)
    return keys


def _best_typeddict_match(
    accessed_keys: Set[str],
    typeddicts: Dict[str, Set[str]],
) -> Optional[tuple]:
    """Return (name, matched_keys) for the TypedDict with most overlap, or None."""
    best_name = None
    best_overlap: Set[str] = set()

    for name, fields in typeddicts.items():
        overlap = accessed_keys & fields
        if len(overlap) >= _MIN_KEY_MATCH and len(overlap) > len(best_overlap):
            best_name = name
            best_overlap = overlap

    return (best_name, best_overlap) if best_name else None
