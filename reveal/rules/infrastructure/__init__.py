"""Infrastructure rules for nginx, terraform, etc.

Constants are defined here for shared use across rules.
"""

import os
import re
from typing import Optional

# Nginx configuration file patterns
# Used by N001, N002, N003 rules
NGINX_FILE_PATTERNS = ['.conf', '.nginx', 'nginx.conf']

# Shared regex for parsing http{} and server{} blocks (one level of nesting).
NGINX_HTTP_BLOCK_PATTERN = re.compile(
    r'http\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
    re.MULTILINE | re.DOTALL,
)
NGINX_INCLUDE_PATTERN = re.compile(r'include\s+([^;]+);', re.IGNORECASE)


def nginx_resolve_include(include_path: str, config_file: str) -> Optional[str]:
    """Resolve a relative nginx include path to an absolute filesystem path.

    Tries the include path relative to the config file's directory, then
    relative to the nginx root (one level up, e.g. /etc/nginx).
    Returns None if the file cannot be found.
    """
    if os.path.isabs(include_path):
        return include_path if os.path.exists(include_path) else None
    config_dir = os.path.dirname(os.path.abspath(config_file)) if config_file else ""
    nginx_root = os.path.dirname(config_dir) if config_dir else ""
    for base in filter(None, [config_dir, nginx_root]):
        candidate = os.path.join(base, include_path)
        if os.path.exists(candidate):
            return candidate
    return None


def nginx_find_nginx_conf(file_path: str) -> Optional[str]:
    """Locate the main nginx.conf relative to a vhost config file.

    Checks (in order): same directory, parent directory, standard system paths.
    Returns None when nginx.conf cannot be found.
    """
    config_dir = os.path.dirname(os.path.abspath(file_path)) if file_path else ""
    nginx_root = os.path.dirname(config_dir) if config_dir else ""
    candidates = [
        os.path.join(config_dir, 'nginx.conf'),
        os.path.join(nginx_root, 'nginx.conf'),
        '/etc/nginx/nginx.conf',
        '/usr/local/nginx/conf/nginx.conf',
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None
