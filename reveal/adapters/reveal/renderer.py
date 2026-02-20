"""Renderer for reveal self-inspection results."""

import sys


class RevealRenderer:
    """Renderer for reveal self-inspection results."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        """Render reveal structure overview.

        Args:
            result: Structure dict from RevealAdapter.get_structure()
            format: Output format ('text', 'json', 'grep')
        """
        from ...rendering import render_reveal_structure
        render_reveal_structure(result, format)

    @staticmethod
    def render_check(result: dict, format: str = 'text', **kwargs) -> None:
        """Render validation check results.

        Args:
            result: Check result dict with detections
            format: Output format ('text', 'json', 'grep')
            **kwargs: Ignored (for compatibility with other adapters' filter flags)
        """
        from ...utils import safe_json_dumps

        detections = result.get('detections', [])
        uri = result.get('file', 'reveal://')

        if format == 'json':
            # Serialize Detection objects to dicts for JSON output
            serialized_result = {
                **result,
                'detections': [d.to_dict() if hasattr(d, 'to_dict') else d for d in detections]
            }
            print(safe_json_dumps(serialized_result))
            return

        if format == 'grep':
            for d in detections:
                print(f"{d.file_path}:{d.line}:{d.column}:{d.rule_code}:{d.message}")
            return

        # Text format
        if not detections:
            print(f"{uri}: ✅ No issues found")
            return

        print(f"{uri}: Found {len(detections)} issues\n")
        for d in sorted(detections, key=lambda x: (x.line, x.column)):
            print(d)
            print()

    @staticmethod
    def render_error(error: Exception) -> None:
        """Render user-friendly errors."""
        print(f"Error inspecting reveal: {error}", file=sys.stderr)
