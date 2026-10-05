"""Text body for patches:// results; format and diagnostics use the shared boundary."""

from typing import Any, Dict

from ..base import BaseRenderer, RenderOptions, capped_section
from ...utils.results import outcome_of


class PatchesRenderer(BaseRenderer):
    """Render patch pressure without writing domain text to stdout."""

    @classmethod
    def _render_text(cls, result: Dict[str, Any], options: RenderOptions = RenderOptions()) -> str:
        if outcome_of(result) == 'failed':
            return ''
        query = result.get('query', {})
        lines = [f"Patch Pressure: {result.get('source', '')}",
                 f"Grouped by: {query.get('group', 'target')}",
                 f"Patch uses: {result.get('total_uses', 0)}  Targets: {result.get('total_targets', 0)}"]
        if query.get('suppress', True):
            lines.append('(sys.stdout/stderr and builtins suppressed — use suppress=false to include)')
        lines.append('')
        groups = result.get('groups', [])
        if not groups:
            lines.extend(['No patch pressure groups found.',
                '  ⚠ Patch detection covers Python (unittest.mock) and '
                "JS/TS (jest/vitest) test suites only — on any other language "
                "this is 'not measured', not 'no patch pressure'."])
        for item in groups:
            lines.extend([str(item.get('key', '<unknown>')),
                f"  patched {item.get('patch_count', 0)} times across {item.get('test_count', 0)} test(s)"])
            if item.get('private_patch_count', 0):
                lines.append(f"  private/internal patches: {item['private_patch_count']}")
            if item.get('max_patches_in_test', 0) > 1:
                lines.append(f"  max patches in one test: {item['max_patches_in_test']}")
            examples = item.get('examples', [])
            if examples:
                lines.append('  examples:')
                lines.extend(capped_section(examples, options.max_examples,
                    lambda ex: f"    {ex.get('test_file')}::{ex.get('test_name')} L{ex.get('line')}"))
            lines.append('')
        return '\n'.join(lines) + '\n'
