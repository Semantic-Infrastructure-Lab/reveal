"""Text renderers for ast://...?show=dict-heatmap and ?show=dict-schemas.

The analysis lives in reveal/analyzers/_python_dict_usage.py, shared with rule T006.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from ...analyzers._python_dict_usage import SCHEMA_MIN_CONSUMERS

_SOURCE_LABELS = {
    'annotated_param': 'param',
    'unannotated_param': 'param, unannotated',
    'loop_var': 'loop var',
    'local': 'local',
    'attribute': 'attribute',
}


def _describe(item: Dict[str, Any]) -> str:
    name = item['param']
    if item.get('source') == 'loop_var':
        return f"for {name} in {item.get('iterable', '')}"
    annotation = item.get('annotation', '')
    return f"{name}: {annotation}" if annotation else name


def render_dict_heatmap(
    items: List[Dict[str, Any]], path: str, unsupported_language: str = '',
) -> str:
    if not items:
        if unsupported_language:
            return (
                f"dict heatmap: Python-only — no .py/.pyi files found in {path}\n"
                f"  (detected {unsupported_language}; this report only analyzes Python source)"
            )
        return (
            f"dict heatmap: no untyped-dict names with key accesses found in {path}\n"
            f"  (a name counts when it's an untyped param, loop variable, or local\n"
            f"   read with string keys: x['k'], x.get('k'), 'k' in x)"
        )

    lines = [
        f"Untyped-dict heatmap — {path}",
        "Ranked by distinct keys read (TypedDict migration priority)",
        '',
    ]
    for item in items:
        keys = item['keys']
        key_preview = ', '.join(keys[:8]) + (', …' if len(keys) > 8 else '')
        source = _SOURCE_LABELS.get(item.get('source', ''), item.get('source', ''))
        lines.append(
            f"  {item['file']}:{item['line']}  {item['function']}({_describe(item)})"
            f"  —  {item['key_count']} keys [{source}]"
        )
        lines.append(f"    keys:      {key_preview}")
        lines.append(f"    suggest:   {item['param']}: {item['suggested_name']}")
        lines.append('')

    by_source = Counter(i.get('source', '') for i in items)
    source_summary = ', '.join(
        f"{n} {_SOURCE_LABELS.get(s, s)}" for s, n in by_source.most_common()
    )
    total_keys = sum(i['key_count'] for i in items)
    lines.append(
        f"  {len(items)} candidate(s) ({source_summary}), {total_keys} total distinct key(s)"
    )
    lines.append('')
    lines.append(f"  → Shared shapes across files: reveal 'ast://{path}?show=dict-schemas'")
    lines.append(f"  → Check for TypedDicts:       reveal check {path} --select T006")
    lines.append(f"  → Trace a name:               reveal 'ast://{path}?reveal_type=<name>'")
    return '\n'.join(lines)


def render_dict_schemas(
    schemas: List[Dict[str, Any]], path: str, unsupported_language: str = '',
) -> str:
    if not schemas:
        if unsupported_language:
            return (
                f"dict schemas: Python-only — no .py/.pyi files found in {path}\n"
                f"  (detected {unsupported_language}; this report only analyzes Python source)"
            )
        return (
            f"dict schemas: no untyped dict shape is read in {SCHEMA_MIN_CONSUMERS}+ "
            f"functions in {path}\n"
            f"  (per-function candidates: reveal 'ast://{path}?show=dict-heatmap')"
        )

    lines = [
        f"Implicit dict schemas — {path}",
        "Untyped dict shapes read in several functions (ranked by files touched)",
        '',
    ]
    for schema in schemas:
        lines.extend(_schema_lines(schema))

    lines.append(f"  {len(schemas)} shared shape(s)")
    lines.append(
        f"  (existing TypedDicts are matched only if defined under {path}"
        " — scan the package root to see them all)"
    )
    lines.append('')
    lines.append(f"  → Per-function detail:      reveal 'ast://{path}?show=dict-heatmap'")
    lines.append(f"  → Params bypassing a match: reveal check {path} --select T006")
    return '\n'.join(lines)


def _schema_lines(schema: Dict[str, Any]) -> List[str]:
    lines = [
        f"  {schema['suggested_name']}  —  {schema['consumer_count']} consumers "
        f"in {schema['file_count']} files  (as: {', '.join(schema['variable_names'][:5])})"
    ]
    key_text = ', '.join(f"{k['key']}×{k['consumers']}" for k in schema['keys'][:12])
    if len(schema['keys']) > 12:
        key_text += ', …'
    lines.append(f"    keys:      {key_text}")
    for match in schema.get('typeddict_matches', []):
        lines.append(
            f"    existing:  {match['name']} ({match['file']}:{match['line']}) covers "
            f"{int(match['coverage'] * 100)}% of core keys — readers still take a plain dict"
        )
        if match['undeclared_keys']:
            undeclared = ', '.join(match['undeclared_keys'][:10])
            if len(match['undeclared_keys']) > 10:
                undeclared += ', …'
            lines.append(f"    drift:     read but not declared on {match['name']}: {undeclared}")
    for consumer in schema['consumers'][:5]:
        lines.append(
            f"    reader:    {consumer['file']}:{consumer['line']}  "
            f"{consumer['function']}({consumer['param']})"
        )
    if len(schema['consumers']) > 5:
        lines.append(f"    …and {len(schema['consumers']) - 5} more (--format json for all)")
    lines.append('')
    return lines
