"""Renderer for patches:// results."""

from __future__ import annotations

from typing import Any, Dict

from reveal.utils import print_json_result


class PatchesRenderer:
    """Render patch pressure scans."""

    @staticmethod
    def render_structure(result: Dict[str, Any], format: str = 'text') -> None:
        if format == 'json':
            print_json_result(result)
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

        from ...utils.warning_render import render_meta_warnings

        groups = result.get('groups', [])
        if not groups:
            # BACK-1261: "No groups found" read as *clean* when it often means
            # *not measured* -- patch detection is Python + jest/vitest only, so
            # on a Ruby, Go or Java repo this line was a confident zero for a
            # question that was never asked. testability:// already prints
            # exactly this disclosure for the identical limitation; patches://
            # printed nothing, on any corpus.
            print("No patch pressure groups found.")
            print(
                "  ⚠ Patch detection covers Python (unittest.mock) and "
                "JS/TS (jest/vitest) test suites only — on any other language "
                "this is 'not measured', not 'no patch pressure'."
            )
            render_meta_warnings(result)
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

        # BACK-1261: W-PATCHES-1 ("patch pressure is advisory") was in the JSON
        # from the start and never printed, so the text render stated findings
        # with more confidence than the contract does.
        render_meta_warnings(result)

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error scanning patches: {error}")
