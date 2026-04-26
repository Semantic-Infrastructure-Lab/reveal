"""Dict usage heatmap for ast://...?show=dict-heatmap.

Scans functions with bare dict parameters, counts distinct key accesses per
param, and returns a ranked list (most keys = most urgent TypedDict candidate).

Output items:
    {
        'file': str,
        'function': str,
        'line': int,
        'param': str,
        'annotation': str,   # 'dict', 'Dict', 'Dict[...]', etc.
        'key_count': int,
        'keys': List[str],   # distinct string keys accessed
        'suggested_name': str,  # e.g. 'trade' -> 'TradeState'
    }
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_BARE_DICT_NAMES = frozenset({'dict', 'Dict'})
_SKIP_DIRS = {
    '.git', '__pycache__', 'node_modules', '.tox', '.venv', 'venv',
    '.mypy_cache', '.pytest_cache', 'dist', 'build', '.eggs',
}


# ─────────────────────────── public entry point ──────────────────────────────

def collect_dict_heatmap(path: str) -> List[Dict[str, Any]]:
    """Return ranked list of bare-dict params with their key access counts."""
    path_obj = Path(path)
    items: List[Dict[str, Any]] = []

    if path_obj.is_file():
        _scan_file(str(path_obj), items)
    elif path_obj.is_dir():
        for root, dirs, files in os.walk(str(path_obj)):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.endswith('.egg-info')]
            for name in files:
                if name.endswith(('.py', '.pyi')):
                    _scan_file(str(Path(root) / name), items)

    # Sort: most keys first (most urgent migration target)
    items.sort(key=lambda x: -x['key_count'])
    return items


# ─────────────────────────── file scanner ────────────────────────────────────

def _scan_file(file_path: str, items: List[Dict[str, Any]]) -> None:
    try:
        content = Path(file_path).read_text(encoding='utf-8', errors='replace')
        tree = ast.parse(content)
    except (SyntaxError, OSError):
        return

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _check_function(node, file_path, items)


def _check_function(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    file_path: str,
    items: List[Dict[str, Any]],
) -> None:
    args = func_node.args
    all_args = (
        args.posonlyargs + args.args + args.kwonlyargs
        + ([args.vararg] if args.vararg else [])
        + ([args.kwarg] if args.kwarg else [])
    )
    for param in all_args:
        if param.arg in ('self', 'cls'):
            continue
        if param.annotation is None:
            continue
        if not _is_bare_dict(param.annotation):
            continue

        annotation_text = ast.unparse(param.annotation)
        keys = _collect_subscript_keys(func_node, param.arg)
        if not keys:
            continue

        items.append({
            'file': file_path,
            'function': func_node.name,
            'line': func_node.lineno,
            'param': param.arg,
            'annotation': annotation_text,
            'key_count': len(keys),
            'keys': sorted(keys),
            'suggested_name': _suggest_typeddict_name(param.arg),
        })


def _is_bare_dict(annotation: ast.expr) -> bool:
    if isinstance(annotation, ast.Name):
        return annotation.id in _BARE_DICT_NAMES
    if isinstance(annotation, ast.Attribute):
        return annotation.attr in _BARE_DICT_NAMES
    if isinstance(annotation, ast.Subscript):
        return _is_bare_dict(annotation.value)
    return False


def _collect_subscript_keys(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    param_name: str,
) -> Set[str]:
    keys: Set[str] = set()
    for node in ast.walk(func_node):
        if not isinstance(node, ast.Subscript):
            continue
        target = node.value
        if not (isinstance(target, ast.Name) and target.id == param_name):
            continue
        idx = node.slice
        if isinstance(idx, ast.Index):
            idx = idx.value  # type: ignore[attr-defined]  # Python 3.8
        if isinstance(idx, ast.Constant) and isinstance(idx.value, str):
            keys.add(idx.value)
    return keys


def _suggest_typeddict_name(param_name: str) -> str:
    """Suggest a TypedDict name from a param name, e.g. 'trade' → 'TradeState'."""
    if not param_name:
        return 'ItemState'
    return param_name.capitalize() + 'State'


# ─────────────────────────── renderer ────────────────────────────────────────

def render_dict_heatmap(items: List[Dict[str, Any]], path: str) -> str:
    if not items:
        return (
            f"dict heatmap: no bare-dict params with key accesses found in {path}\n"
            f"  (functions must be annotated as `param: dict` or `param: Dict[...]`\n"
            f"   and access keys via param['key'] for this report to fire)"
        )

    lines = [f"Bare-dict heatmap — {path}", f"Ranked by distinct key accesses (TypedDict migration priority)", '']

    for item in items:
        func = item['function']
        param = item['param']
        annotation = item['annotation']
        key_count = item['key_count']
        keys = item['keys']
        suggested = item['suggested_name']
        file_path = item['file']
        line = item['line']

        key_preview = ', '.join(keys[:8])
        if len(keys) > 8:
            key_preview += ', …'

        lines.append(
            f"  {file_path}:{line}  {func}({param}: {annotation})"
            f"  —  {key_count} keys"
        )
        lines.append(f"    keys:      {key_preview}")
        lines.append(f"    suggest:   {param}: {suggested}")
        lines.append('')

    total_keys = sum(i['key_count'] for i in items)
    lines.append(f"  {len(items)} candidate(s), {total_keys} total key access(es)")
    lines.append('')
    lines.append(f"  → Check for TypedDicts: reveal --check {path} --rules T006")
    lines.append(f"  → Trace a param:        reveal 'ast://{path}?reveal_type=<param>'")

    return '\n'.join(lines)
