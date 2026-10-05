"""Renderer for reveal self-inspection results."""


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
    def render_element(result: dict, format: str = 'text') -> None:
        """Render one element of a reveal source file, as the file view prints one."""
        if format == 'json':
            from ...utils import print_json_result
            print_json_result(result)
            return
        start = result.get('line_start', 1)
        print(f"reveal://{result.get('file')}:{start}-{result.get('line_end')} | {result.get('element')}\n")
        for offset, line in enumerate(str(result.get('content', '')).splitlines()):
            print(f"{start + offset:>6}  {line}")

    @staticmethod
    def render_check(result: dict, format: str = 'text', **kwargs) -> None:
        """Render validation check results.

        Args:
            result: Check result dict with detections
            format: Output format ('text', 'json', 'grep')
            **kwargs: Ignored (for compatibility with other adapters' filter flags)
        """
        from ...utils import print_json_result

        detections = result.get('detections', [])
        uri = result.get('file', 'reveal://')

        if format == 'json':
            # Serialize Detection objects to dicts for JSON output
            serialized_result = {
                **result,
                'detections': [d.to_dict() if hasattr(d, 'to_dict') else d for d in detections]
            }
            print_json_result(serialized_result)
            return

        if format == 'grep':
            for d in detections:
                print(f"{d.file_path}:{d.line}:{d.column}:{d.rule_code}:{d.message}")
            return

        # Text format
        coverage = result.get("coverage", {})
        if coverage:
            print(f"Checks: {coverage['run']} run, {coverage['skipped']} skipped, {coverage['failed']} failed, "
                  f"{coverage.get('unavailable', 0)} unavailable")
            print(coverage["scope"])
            for entry in coverage.get("rules", []):
                if entry["status"] == "unavailable":
                    print(f"  {entry['rule']} unavailable: {entry['reason']}")
                for subject in entry.get("subjects", []):
                    if subject["status"] != "run" and subject["subject"]:
                        print(f"    {subject['subject']} {subject['status']}: {subject['reason']}")
        if result.get("error"):
            print(f"{uri}: Self-check incomplete")
            for error in result.get("errors", []):
                print(f"  {error['rule']}: {error['error']}")
        if not detections:
            if not result.get("error"):
                print(f"{uri}: ✅ No issues found in completed checks")
            return

        print(f"{uri}: Found {len(detections)} issues\n")
        for d in sorted(detections, key=lambda x: (x.line, x.column)):
            print(d)
            print()
