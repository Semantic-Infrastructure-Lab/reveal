"""Structure retrieval for reveal adapter."""

from pathlib import Path
from typing import Dict, List, Any, Optional

from ..base import _ADAPTER_REGISTRY


def get_structure(reveal_root: Path, component: Optional[str] = None, **kwargs: Any) -> Dict[str, Any]:
    """Get reveal's internal structure.

    Args:
        reveal_root: Path to reveal's root directory
        component: Optional component to filter by (analyzers, adapters, rules, config)
        **kwargs: Additional arguments (unused)

    Returns:
        Dict containing analyzers, adapters, rules, etc.
        Filtered by component if specified.
    """
    # Filter by component if specified
    if component:
        component = component.lower()

        if component == 'analyzers':
            analyzers = get_analyzers(reveal_root)
            return {
                'contract_version': '1.0',
                'type': 'reveal_structure',
                'source': str(reveal_root),
                'source_type': 'directory',
                'analyzers': analyzers,
                'metadata': {
                    'root': str(reveal_root),
                    'analyzers_count': len(analyzers),
                }
            }
        elif component == 'adapters':
            adapters = get_adapters()
            return {
                'contract_version': '1.0',
                'type': 'reveal_structure',
                'source': str(reveal_root),
                'source_type': 'directory',
                'adapters': adapters,
                'metadata': {
                    'root': str(reveal_root),
                    'adapters_count': len(adapters),
                }
            }
        elif component == 'rules':
            rules = get_rules(reveal_root)
            return {
                'contract_version': '1.0',
                'type': 'reveal_structure',
                'source': str(reveal_root),
                'source_type': 'directory',
                'rules': rules,
                'metadata': {
                    'root': str(reveal_root),
                    'rules_count': len(rules),
                }
            }
        elif component == 'config':
            from .config import get_config
            config_data = get_config(reveal_root)
            return {
                'contract_version': '1.0',
                'type': 'reveal_structure',
                'source': str(reveal_root),
                'source_type': 'directory',
                **config_data
            }

    # Default: show everything
    analyzers = get_analyzers(reveal_root)
    adapters = get_adapters()
    rules = get_rules(reveal_root)

    structure = {
        'contract_version': '1.0',
        'type': 'reveal_structure',
        'source': str(reveal_root),
        'source_type': 'directory',
        'analyzers': analyzers,
        'adapters': adapters,
        'rules': rules,
        'supported_file_types': get_supported_types(reveal_root),
        'metadata': {
            'root': str(reveal_root),
            'analyzers_count': len(analyzers),
            'adapters_count': len(adapters),
            'rules_count': len(rules),
        }
    }

    return structure


def get_analyzers(reveal_root: Path) -> List[Dict[str, Any]]:
    """Get all registered analyzers.

    Args:
        reveal_root: Path to reveal's root directory

    Returns:
        List of analyzer metadata dicts
    """
    analyzers: List[Dict[str, Any]] = []
    analyzers_dir = reveal_root / 'analyzers'

    if not analyzers_dir.exists():
        return analyzers

    for file in analyzers_dir.glob('*.py'):
        if file.stem.startswith('_'):
            continue

        analyzers.append({
            'name': file.stem,
            'path': str(file.relative_to(reveal_root)),
            'module': f'reveal.analyzers.{file.stem}'
        })

    return sorted(analyzers, key=lambda x: x['name'])


def get_adapters() -> List[Dict[str, Any]]:
    """Get all registered adapters from the registry.

    Returns:
        List of adapter metadata dicts
    """
    adapters = []

    for scheme, adapter_class in _ADAPTER_REGISTRY.items():
        adapters.append({
            'scheme': scheme,
            'class': adapter_class.__name__,
            'module': adapter_class.__module__,
            'has_help': hasattr(adapter_class, 'get_help')
        })

    return sorted(adapters, key=lambda x: x['scheme'])


def get_rules(reveal_root: Path) -> List[Dict[str, Any]]:
    """Get all available rules.

    Args:
        reveal_root: Path to reveal's root directory

    Returns:
        List of rule metadata dicts
    """
    rules: List[Dict[str, Any]] = []
    rules_dir = reveal_root / 'rules'

    if not rules_dir.exists():
        return rules

    for category_dir in rules_dir.iterdir():
        if not category_dir.is_dir() or category_dir.name.startswith('_'):
            continue

        for rule_file in category_dir.glob('*.py'):
            if rule_file.stem.startswith('_'):
                continue

            rules.append({
                'code': rule_file.stem,
                'category': category_dir.name,
                'path': str(rule_file.relative_to(reveal_root)),
                'module': f'reveal.rules.{category_dir.name}.{rule_file.stem}'
            })

    return sorted(rules, key=lambda x: x['code'])


def get_supported_types(reveal_root: Path) -> List[str]:
    """Get list of supported file extensions.

    Args:
        reveal_root: Path to reveal's root directory

    Returns:
        List of supported analyzer names
    """
    # This would ideally query the analyzer registry
    # For now, return a basic list
    types = []

    # Scan analyzer files for @register decorators
    analyzers_dir = reveal_root / 'analyzers'
    if analyzers_dir.exists():
        for file in analyzers_dir.glob('*.py'):
            if file.stem.startswith('_'):
                continue
            # We could parse the file to extract @register patterns
            # For now, just note the analyzer exists
            types.append(file.stem)

    return sorted(types)
