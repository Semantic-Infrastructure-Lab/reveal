"""Operations (check) for reveal adapter. Element extraction: RevealAdapter.get_element."""

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
