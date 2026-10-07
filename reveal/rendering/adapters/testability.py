"""Text body for testability:// results; JSON and failures use the shared boundary."""

from typing import Any, Dict, List, Optional

from ..base import BaseRenderer
from ...utils import print_json_result
from ...utils.results import outcome_of


def patch_hotspot_lines(rows: List[Dict[str, Any]], note: str = '') -> List[str]:
    lines = ["Production Patch Hotspots"]
    if not rows:
        lines.append(f"  {note}" if note else "  none above threshold")
        lines.append("")
        return lines
    for row in rows:
        lines.append("")
        lines.append(f"  {row.get('key')}")
        lines.append(
            f"    patched {row.get('patch_count', 0)} times across "
            f"{row.get('test_count', 0)} test(s)"
        )
        categories = row.get('boundary_categories') or []
        if categories:
            lines.append(f"    boundary categories: {', '.join(categories)}")
        profiles = row.get('related_profiles') or []
        if profiles:
            # JSON lists every profile; the header says when text shows only 3 (BACK-1551).
            shown = f" (3 of {len(profiles)}; --format json lists all)" if len(profiles) > 3 else ""
            lines.append(f"    related production functions{shown}:")
            for profile in profiles[:3]:
                lines.append(
                    f"      {profile.get('file')}::{profile.get('function')} "
                    f"(cx {profile.get('complexity')}, line {profile.get('line')})"
                )
        lines.append(f"    suggestion: {row.get('suggestion')}")
    lines.append("")
    return lines


def boundary_hotspot_lines(rows: List[Dict[str, Any]]) -> List[str]:
    lines = ["Boundary Fan-Out Hotspots"]
    if not rows:
        lines.append("  none above threshold")
        lines.append("")
        return lines
    for row in rows:
        lines.append("")
        lines.append(f"  {row.get('file')}::{row.get('function')}")
        lines.append(f"    complexity: {row.get('complexity')}  lines: {row.get('lines')}")
        lines.append(f"    categories: {', '.join(row.get('categories', []))}")
        if row.get('patch_count'):
            lines.append(f"    related patch pressure: {row.get('patch_count')} patches")
        lines.append(f"    suggestion: {row.get('suggestion')}")
    lines.append("")
    return lines


def testability_text(report: Dict[str, Any]) -> str:
    summary = report.get('summary', {})
    lines = [
        f"Testability: {report.get('source')}",
        f"Tests: {', '.join(report.get('tests', []))}",
        "-" * 50,
        f"Patch uses: {summary.get('total_patch_uses', 0)}  "
        f"Patch targets: {summary.get('total_patch_targets', 0)}",
        "",
    ]
    lines += patch_hotspot_lines(report.get('patch_hotspots', []), note=report.get('_patch_note', ''))
    lines += boundary_hotspot_lines(report.get('boundary_hotspots', []))
    lines += [
        "Summary",
        f"  {summary.get('patch_groups_reported', 0)} patch hotspot(s) reported",
        f"  {summary.get('boundary_profiles_reported', 0)} boundary hotspot(s) reported",
    ]
    return "\n".join(lines)


class TestabilityRenderer(BaseRenderer):
    """Renderer for testability:// results."""

    __test__ = False  # not a pytest class

    @classmethod
    def render_structure(cls, result: Dict[str, Any], format: str = 'text') -> Optional[str]:
        if format == 'json':
            print_json_result(result)
            return None
        if outcome_of(result) == 'failed':
            return super().render_structure(result, format)
        return testability_text(result)

    @classmethod
    def _render_text(cls, result: Dict[str, Any]) -> str:
        return testability_text(result)
