"""Render a ``--grep`` result (``reveal.grep_handler``): text or JSON.

Every hit is shown with its line's text, under the element it falls in (BACK-1602):

    File: adapters/depends.py
      (top level)
          26: from ..utils.results import note_truncation
      _format_file_dependents()
        1594: note_truncation(result, 'dependents', len(shown), total)

A hit outside any element is listed under "(top level)"; a flat file's hits have no label. The header counts every
hit; when the hits shown were cut, the router prints the ``⚠ Truncated hits: ...`` line after
this (``print_result_control_notes``), so no renderer here says it.
"""

from pathlib import Path
from typing import Any, Dict, List

from ..utils import safe_json_dumps


def render_grep(result: Dict[str, Any], output_format: str) -> None:
    if output_format == 'json':
        print(safe_json_dumps(_json_view(result)))
    elif result.get('error'):
        return  # the router has reported it
    elif 'files' in result:
        _render_dir_text(result)
    else:
        _render_file_text(result)


def _json_groups(groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{'name': g['name'], 'kind': g['kind'], 'lines': g['lines'], 'hits': g['hits']}
            for g in groups]


def _json_view(result: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(result)
    if 'groups' in out:
        out['groups'] = _json_groups(out['groups'])
    if 'files' in out:
        out['files'] = [dict(f, groups=_json_groups(f['groups'])) for f in out['files']]
    return out


def _label(group: Dict[str, Any]) -> str:
    if group.get('kind') == 'section':
        return f"{'#' * (group.get('level') or 1)} {group['name']}"
    return f"{group['name']}()"


def _print_groups(groups: List[Dict[str, Any]]) -> None:
    """Labels at two spaces, hits under them at four. Hits outside any element get a
    "(top level)" label when the file has named groups, so a padded line number can't
    read as part of the group above; a flat file's hits stand alone at two spaces."""
    width = len(str(max((h['line'] for g in groups for h in g['hits']), default=0)))
    labelled = any(g['name'] for g in groups)
    for group in groups:
        indent = '  '
        if labelled:
            print(f"  {_label(group) if group['name'] else '(top level)'}")
            indent = '    '
        for hit in group['hits']:
            print(f"{indent}{hit['line']:>{width}}: {hit['text']}")


def _no_match_tips(result: Dict[str, Any], lines: List[str]) -> None:
    import re
    pattern = result['pattern']
    if result.get('hint'):
        lines.append(f"  Tip: {result['hint']}")
    elif 'files' not in result and not re.search(r'[|+*?\\[\]{}()]', pattern):
        lines.append(f"  Tip: --grep searches literal/regex text. "
                     f"For named elements use: reveal {result['path']} --name '{pattern}'")
    print("\n".join(lines))


def _hit_word(n: int) -> str:
    return "hit" if n == 1 else "hits"


def _render_file_text(result: Dict[str, Any]) -> None:
    total = result['total_hits']
    groups = result['groups']
    print(f"Text search: {result['path']}  —  pattern: {result['pattern']}")
    if not total:
        _no_match_tips(result, ["No matches found."])
        return
    named = [g for g in groups if g['name']]
    count = result.get('elements_matched', len(named))
    if count:
        unit = "section" if named and named[0].get('kind') == 'section' else "element"
        print(f"{total} {_hit_word(total)} in {count} {unit}{'' if count == 1 else 's'}")
    else:
        print(f"{total} {_hit_word(total)}")
    print()
    _print_groups(groups)


def _render_dir_text(result: Dict[str, Any]) -> None:
    from ..tree_view import _format_suppressed_footer  # noqa: I006 -- tree_view imports display
    from collections import Counter
    total = result['total_hits']
    matched = result.get('files_matched', len(result['files']))
    print(f"Text search: {result['path']}  —  pattern: {result['pattern']}")
    if not matched:
        searched = result.get('files_searched')
        lines = ["No matches found." if searched is None else
                 f"No matches found in {searched} file{'' if searched == 1 else 's'}."]
        footer = _format_suppressed_footer(Counter(result.get('hidden') or {}))
        if footer:
            lines.append(f"  {footer}")
        _no_match_tips(result, lines)
        return
    print(f"{total} {_hit_word(total)} across {matched} file{'' if matched == 1 else 's'}")
    print()
    base = Path(result['path'])
    for i, entry in enumerate(result['files']):
        if i:
            print()
        print(f"File: {Path(entry['path']).relative_to(base).as_posix()}")
        _print_groups(entry['groups'])
