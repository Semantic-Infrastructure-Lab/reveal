"""Configuration retrieval for reveal adapter."""

import os
from pathlib import Path
from typing import Dict, Any


def get_config(reveal_root: Path) -> Dict[str, Any]:
    """Get current configuration with full transparency.

    Args:
        reveal_root: Path to reveal's root directory

    Returns:
        Dict containing active config, sources, and metadata
    """
    from ...config import RevealConfig

    # Get current config instance
    config = RevealConfig.get()

    # Extract environment variables
    env_vars = {}
    env_var_names = [
        'REVEAL_NO_CONFIG',
        'REVEAL_CONFIG',
        'REVEAL_RULES_DISABLE',
        'REVEAL_C901_THRESHOLD',
        'REVEAL_C905_MAX_DEPTH',
        'REVEAL_E501_MAX_LENGTH',
        'REVEAL_M101_THRESHOLD',
        'REVEAL_CONFIG_DEBUG'
    ]
    for var in env_var_names:
        value = os.getenv(var)
        if value:
            env_vars[var] = value

    # Discover config files
    project_configs = []
    try:
        discovered = RevealConfig._discover_project_configs(Path.cwd())
        for cfg in discovered:
            if 'path' in cfg:
                project_configs.append({
                    'path': str(cfg['path']),
                    'root': cfg.get('root', False)
                })
    except Exception:
        pass

    # Check user and system configs
    user_config_path = RevealConfig._get_user_config_path()
    system_config_path = Path('/etc/reveal/config.yaml')

    custom_config = os.getenv('REVEAL_CONFIG')

    return {
        'active_config': {
            'rules': config._config.get('rules', {}),
            'ignore': config._config.get('ignore', []),
            'root': config._config.get('root', False),
            'overrides': config._config.get('overrides', []),
            'architecture': config._config.get('architecture', {}),
            'adapters': config._config.get('adapters', {}),
        },
        'sources': {
            'env_vars': env_vars,
            'custom_config': custom_config,
            'project_configs': project_configs,
            'user_config': str(user_config_path)
            if user_config_path.exists() else None,
            'system_config': str(system_config_path)
            if system_config_path.exists() else None,
        },
        'metadata': {
            'project_root': str(config.project_root),
            'working_directory': str(Path.cwd()),
            'no_config_mode': os.getenv('REVEAL_NO_CONFIG') == '1',
            'env_vars_count': len(env_vars),
            'config_files_count': len(project_configs),
            'custom_config_used': custom_config is not None,
        },
        'precedence_order': [
            '1. CLI flags (--select, --ignore)',
            '2. Environment variables',
            '3. Custom config file (REVEAL_CONFIG)',
            '4. Project configs (from cwd upward)',
            '5. User config (~/.config/reveal/config.yaml)',
            '6. System config (/etc/reveal/config.yaml)',
            '7. Built-in defaults'
        ]
    }
