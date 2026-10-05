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
    from reveal.reveal_types import CONTRACT_VERSION

    from ...rules import RuleRegistry

    # V-series rules inspect reveal source directly
    errors: List[Dict[str, str]] = []
    coverage: List[Dict[str, str]] = []
    detections = RuleRegistry.check_file("reveal://", None, "", select=select, ignore=ignore,
                                         errors=errors, coverage=coverage)

    result: Dict[str, Any] = {
        'contract_version': CONTRACT_VERSION,
        'type': 'reveal_check',
        'source': 'reveal://',
        'source_type': 'runtime',
        'file': 'reveal://',
        'detections': detections,  # Keep as Detection objects for render_check
        'total': len(detections),
        'coverage': {
            'scope': 'Rule execution only; legacy rules may skip internal prerequisites. '
                     'V035 uses a recorded stats fixture, not all adapter renderers.',
            'rules': coverage,
            'run': sum(entry['status'] == 'run' for entry in coverage),
            'skipped': sum(entry['status'] == 'skipped' for entry in coverage),
            'failed': len(errors),
        },
        'errors': errors
    }

    if errors or not result['coverage']['run']:
        result['error'] = 'Self-check incomplete: rules failed or no applicable rules ran'
    result['exit_code'] = 1 if detections or result.get('error') else 0
    return result
