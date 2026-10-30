"""Configuration retrieval for reveal adapter."""

import os
from pathlib import Path
from typing import Dict, Any, Optional

from ...utils.path_utils import TestLayout, to_posix


def get_config(reveal_root: Optional[Path] = None) -> Dict[str, Any]:
    """Get current configuration with full transparency.

    Every source listed is one RevealConfig actually read (``RevealConfig.sources``) and every
    variable under ``env_vars`` is one its loader reads (``CONFIG_ENV_VARS``), so the view
    cannot drift from the loader (BACK-2275).

    Args:
        reveal_root: Unused; the config shown is the one for the current directory

    Returns:
        Dict containing active config, sources, and metadata
    """
    from ...config import CONFIG_ENV_VARS, CUSTOM_CONFIG_ENV, NO_CONFIG_ENV, RevealConfig, config_env_vars

    # Get current config instance
    config = RevealConfig.get()

    layout = TestLayout.for_path(Path.cwd(), fallback_root=Path.cwd())
    test_layout = config.inspect_test_layout(layout)

    env_vars = config_env_vars()
    # Set REVEAL_* variables the config loader does not read (cache, workers, a misspelling):
    # shown apart so a variable that has no effect on the config is not mistaken for one.
    other_env_vars = {
        name: value for name, value in sorted(os.environ.items())
        if name.startswith('REVEAL_') and name not in CONFIG_ENV_VARS and value
    }

    def read_file(layer: str) -> Optional[str]:
        return next((to_posix(s.path) for s in config.sources if s.layer == layer), None)

    # nearest first, the order discovery walks
    project_configs = [
        {'path': to_posix(s.path), 'root': s.root}
        for s in reversed(config.sources) if s.layer == 'project'
    ]

    custom_config = os.getenv(CUSTOM_CONFIG_ENV)

    return {
        'test_layout': test_layout,
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
            'other_env_vars': other_env_vars,
            'custom_config': custom_config,
            'project_configs': project_configs,
            'user_config': read_file('user'),
            'system_config': read_file('system'),
            'load_failures': [
                {'path': to_posix(path), 'reason': why} for path, why in config.load_failures
            ],
        },
        'metadata': {
            'project_root': to_posix(config.project_root),
            'test_layout_anchor': to_posix(layout.anchor),
            'working_directory': to_posix(Path.cwd()),
            'no_config_mode': os.getenv(NO_CONFIG_ENV) == '1',
            'env_vars_count': len(env_vars),
            'config_files_count': len(config.sources),
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
