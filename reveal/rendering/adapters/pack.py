"""Returned pack text for CLI, URI and MCP consumers."""
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..base import BaseRenderer, capped_section
from ...utils.results import outcome_of
from ...utils.warning_render import meta_warning_lines

def _format_architecture_brief(selected: List[Dict[str, Any]]) -> List[str]:
    """Format a concise architecture hint derived from fan-in and priority."""
    entry_points = [
        f['relative'] for f in selected
        if not f.get('changed') and f.get('priority', 0) >= 8
    ]
    core = sorted(
        [f for f in selected if f.get('fan_in', 0) >= 5],
        key=lambda f: -f.get('fan_in', 0),
    )

    lines = ['── Architecture Hint ──']
    if entry_points:
        lines.append(f"Entry points:      {', '.join(entry_points)}")
    if core:
        abstractions = '  '.join(capped_section(
            core, 5, lambda f: f"{f['relative']}({f['fan_in']})", indent=''))
        lines.append(f"Core abstractions: {abstractions}")
    if not entry_points and not core and selected:
        top = sorted(selected, key=lambda f: -f.get('priority', 0))
        lines.append(f"Top files:         {', '.join(capped_section(top, 3, lambda f: f['relative'], indent=''))}")
    lines.append('')
    return lines


def _format_file_line(f: Dict[str, Any], verbose: bool = True) -> str:
    """Format one file entry as a string (verbose form, for MCP / string consumers)."""
    if not verbose:
        return f"  {f['relative']}"
    lines = '?' if f['lines'] is None else f['lines']
    return f"  {f['relative']:50} {f['tokens_approx']:5} tokens  {lines:>4} lines"


def _candidate_discovery_incomplete(meta: Dict[str, Any]) -> bool:
    return any(warning.get('type') == 'analysis_incomplete' and warning.get('unit') == 'directories'
               for warning in meta.get('warnings') or [])


def _stat_measurement_incomplete(meta: Dict[str, Any]) -> bool:
    return any(warning.get('type') == 'file_measurement_failed' and 'stat' in warning.get('operations', [])
               for warning in meta.get('warnings') or [])


def _used_line_total(meta: Dict[str, Any]) -> str:
    return 'unavailable' if meta['used_lines'] is None else str(meta['used_lines'])


def _pack_empty_line(meta: Dict[str, Any]) -> str:
    stat_incomplete = _stat_measurement_incomplete(meta)
    if stat_incomplete and meta['total_candidates'] == 0:
        return 'No eligible files were measured; candidate file measurements are unavailable.'
    if meta.get('line_budget_incomplete'):
        return 'No files selected: line costs are unavailable or exceed the budget.'
    if stat_incomplete:
        return 'No observed measured eligible files fit within budget; file measurements are incomplete.'
    if not _candidate_discovery_incomplete(meta):
        return 'No files fit within budget.'
    if meta['total_candidates'] == 0:
        return ('No eligible files were observed; the candidate population is unavailable '
                'because directory discovery was incomplete.')
    return 'No observed eligible files fit within budget; candidate discovery is incomplete.'


def _format_pack_header(
    path: Path,
    meta: Dict[str, Any],
    budget_tokens: Optional[int],
    budget_lines: Optional[int],
    since_error: Optional[str],
) -> List[str]:
    """Format the pack header (budget + since + selected counts) as lines."""
    since_val = meta.get('since')
    budget_desc = f"~{budget_tokens} tokens" if budget_tokens else f"{budget_lines} lines"
    since_desc = f"  [since {since_val}]" if since_val else ""
    lines = [f"Pack: {path}  [{budget_desc} budget]{since_desc}"]
    if since_val:
        lines.append(f"Changed files:  {meta.get('changed_files_count', 0)} (boosted to top priority)")
    if since_error:
        lines.append(f"Warning: --since: {since_error}")
    file_label = ('observed eligible files' if _candidate_discovery_incomplete(meta)
                  or _stat_measurement_incomplete(meta) else 'files')
    lines.append(
        f"Selected {meta['selected']} of {meta['total_candidates']} {file_label} "
        f"(~{meta['used_tokens_approx']} tokens, {_used_line_total(meta)} lines)"
    )
    lines.append("")
    return lines


def _format_pack_file_groups(selected: List[Dict[str, Any]], meta: Dict[str, Any],
                             verbose: bool = True) -> List[str]:
    """Format the tiered file listing (changed/high/medium/low) as lines."""
    since_val = meta.get('since')
    groups = [
        (f"── Changed files (since {since_val}) ──",
         [f for f in selected if f.get('changed')]),
        ("── Entry points / focus files ──",
         [f for f in selected if not f.get('changed') and f['priority'] >= 8]),
        ("── Key modules ──",
         [f for f in selected if not f.get('changed') and 2 <= f['priority'] < 8]),
        ("── Other files ──",
         [f for f in selected if not f.get('changed') and f['priority'] < 2]),
    ]
    lines: List[str] = []
    for header, files in groups:
        if files:
            lines.append(header)
            lines.extend(_format_file_line(f, verbose) for f in files)
            lines.append("")
    if meta['skipped'] > 0:
        reason = ('budget exceeded or line cost unavailable' if meta.get('line_budget_incomplete')
                  else 'exceeded budget')
        lines.append(f"[{meta['skipped']} files excluded — {reason}]")
    return lines


def _content_lines(content_data: List[Dict[str, Any]]) -> List[str]:
    """Format the per-file content section (changed=full, key=structure, low=names)."""
    lines = [
        "",
        "━" * 70,
        "CONTENT  (changed=full · key files=structure · low priority=names)",
        "━" * 70,
    ]
    name_only: List[str] = []
    for entry in content_data:
        if entry['content_type'] == 'name_only':
            name_only.append(entry['file'])
            continue
        marker = "  ◀ CHANGED (full content)" if entry['content_type'] == 'full' else ""
        lines.append(f"\n── {entry['file']}{marker} ──")
        if entry.get('error'):
            lines.append(f"[{entry['error']}]")
        else:
            empty = "[empty]" if entry['content_type'] == 'full' else "[no structure analysis available]"
            lines.append(entry['content'].removesuffix('\n') if entry['content'].strip() else empty)
    if name_only:
        lines.append("\n── Low-priority files (selected, structure omitted) ──")
        lines.extend(f"  {f}" for f in name_only)
    return lines


def _format_pack_content(selected: List[Dict[str, Any]]) -> List[str]:
    from ...adapters.pack import _collect_file_contents
    # MCP's historical string helper trims trailing content whitespace.
    entries = _collect_file_contents(selected)
    return _content_lines([{**entry, 'content': entry['content'].rstrip()} for entry in entries])


def _format_pack_result(
    path: Path,
    selected: List[Dict[str, Any]],
    meta: Dict[str, Any],
    budget_tokens: Optional[int],
    budget_lines: Optional[int],
    since_error: Optional[str] = None,
    content: bool = True,
    architecture: bool = False,
) -> str:
    """Format the MCP snapshot, preserving its existing helper interface."""
    body = pack_text(path, selected, meta, True, budget_tokens, budget_lines,
                     architecture, since_error).removesuffix('\n')
    if content and selected:
        body += "\n" + "\n".join(_format_pack_content(selected))
    warning_lines = meta_warning_lines({'meta': meta})
    if warning_lines:
        body += "\n" + "\n".join(warning_lines)
    return body


def pack_text(path: Path, selected: List[Dict[str, Any]], meta: Dict[str, Any],
              verbose: bool, budget_tokens: Optional[int], budget_lines: Optional[int],
              architecture: bool = False, since_error: Optional[str] = None) -> str:
    """Format the CLI inventory without emitting or reading content."""
    lines = _format_pack_header(path, meta, budget_tokens, budget_lines, since_error)
    if not selected:
        lines.append(_pack_empty_line(meta))
    else:
        if architecture:
            lines.extend(_format_architecture_brief(selected))
        lines.extend(_format_pack_file_groups(selected, meta, verbose))
    return "\n".join(lines) + "\n"


class PackRenderer(BaseRenderer):
    """Pack presentation; the shared boundary owns emission and failures."""

    @classmethod
    def render_structure(cls, result: Dict[str, Any], format: str = 'text',
                         verbose: bool = False, architecture: bool = False,
                         content: bool = False) -> Optional[str]:
        if format == 'json' or outcome_of(result) == 'failed':
            return super().render_structure(result, format)
        return cls._pack_body(result, verbose, architecture, content)

    @classmethod
    def _pack_body(cls, result: Dict[str, Any], verbose: bool = False,
                   architecture: bool = False, content: bool = False) -> str:
        meta = result['meta']
        body = pack_text(Path(result['path']), result['files'], meta,
                         result.get('verbose', verbose), meta.get('budget_tokens'),
                         meta.get('budget_lines'), result.get('architecture', architecture))
        if content or 'content' in result:
            body += "\n".join(_content_lines(result.get('content', []))) + "\n"
        return body

    @classmethod
    def _render_text(cls, result: Dict[str, Any]) -> str:
        return cls._pack_body(result)
