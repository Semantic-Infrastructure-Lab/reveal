"""Operations (check, element extraction) for reveal adapter."""

from pathlib import Path
from typing import Dict, List, Any, Optional


def check(select: Optional[List[str]] = None, ignore: Optional[List[str]] = None) -> Dict[str, Any]:
    """Run validation rules on reveal itself.

    Args:
        select: Optional list of rule codes to run
        ignore: Optional list of rule codes to ignore

    Returns:
        Dict with detections and metadata
    """
    from ...rules import RuleRegistry

    # V-series rules inspect reveal source directly
    detections = RuleRegistry.check_file("reveal://", None, "", select=select, ignore=ignore)

    return {
        'file': 'reveal://',
        'detections': detections,  # Keep as Detection objects for render_check
        'total': len(detections)
    }


def get_element(reveal_root: Path, element_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
    """Extract a specific element from a reveal source file.

    Args:
        reveal_root: Path to reveal's root directory
        element_name: Element to extract (e.g., function name) or resource path
        **kwargs: Optional keyword arguments:
            - resource: File path within reveal (e.g., "rules/links/L001.py")
            - args: Command-line arguments

    Returns:
        Dict with success status if successful, None if failed
    """
    from ...file_handler import handle_file

    # For backwards compatibility, support resource as kwarg
    resource = kwargs.get('resource', element_name)
    args = kwargs.get('args')

    if not args:
        # If no args provided, return None (cannot process)
        return None

    # Resolve the file path within reveal
    file_path = reveal_root / resource

    # Backward compatibility: redirect old reveal.py path to new adapter.py
    if not file_path.exists() and resource == 'adapters/reveal.py':
        file_path = reveal_root / 'adapters' / 'reveal' / 'adapter.py'

    if not file_path.exists():
        return None

    # Use regular file processing to extract the element
    # This delegates to the appropriate analyzer (Python, etc.)
    try:
        handle_file(str(file_path), element_name,
                   show_meta=False, output_format=args.format, args=args)
        return {'success': True}
    except Exception:
        return None
