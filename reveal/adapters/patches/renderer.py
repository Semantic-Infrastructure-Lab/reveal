"""Renderer for patches:// results."""

from __future__ import annotations

from typing import Any, Dict

from reveal.utils import safe_json_dumps


class PatchesRenderer:
    """Render patch pressure scans."""

    @staticmethod
    def render_structure(result: Dict[str, Any], format: str = 'text') -> None:
        if format == 'json':
            print(safe_json_dumps(result))
            return

        source = result.get('source', '')
        query = result.get('query', {})
        group = query.get('group', 'target')
        suppress = query.get('suppress', True)
        print(f"Patch Pressure: {source}")
        print(f"Grouped by: {group}")
        print(f"Patch uses: {result.get('total_uses', 0)}  Targets: {result.get('total_targets', 0)}")
        if suppress:
            print("(sys.stdout/stderr and builtins suppressed — use suppress=false to include)")
        print()

        groups = result.get('groups', [])
        if not groups:
            print("No patch pressure groups found.")
            return

        for item in groups:
            print(f"{item.get('key', '<unknown>')}")
            print(
                f"  patched {item.get('patch_count', 0)} times across "
                f"{item.get('test_count', 0)} test(s)"
            )
            private_count = item.get('private_patch_count', 0)
            if private_count:
                print(f"  private/internal patches: {private_count}")
            if item.get('max_patches_in_test', 0) > 1:
                print(f"  max patches in one test: {item.get('max_patches_in_test')}")
            examples = item.get('examples', [])
            if examples:
                print("  examples:")
                for ex in examples[:3]:
                    print(f"    {ex.get('test_file')}::{ex.get('test_name')} L{ex.get('line')}")
            print()

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error scanning patches: {error}")
