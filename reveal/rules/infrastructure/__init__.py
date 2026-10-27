"""Infrastructure rules for nginx, terraform, etc.

Constants are defined here for shared use across rules.
"""

import os
import re
from typing import Iterator, Optional

from ...utils.nginx_conf import find_blocks, top_level_statements

# Nginx configuration file patterns
# Used by N001, N002, N003 rules
NGINX_FILE_PATTERNS = ['.conf', '.nginx', 'nginx.conf']

NGINX_INCLUDE_PATTERN = re.compile(r'include\s+([^;]+);', re.IGNORECASE)


# A whole-line nginx comment: optional leading whitespace, then '#' to end of
# line. Does NOT match a trailing comment after real directive text on the
# same line (nginx allows both forms; only whole-line comments are common
# enough for "commented-out server{} block" scaffolding to be worth the
# preprocessing pass -- BACK-1102/BACK-1103). Excludes reveal's own
# suppression-marker comments (`# reveal:allow-...`) -- those are directives
# TO reveal, not disabled nginx config, and rules must still see them after
# stripping.
_NGINX_COMMENT_LINE_RE = re.compile(r'^[ \t]*#(?!\s*reveal:).*$', re.MULTILINE)


def nginx_strip_comments(content: str) -> str:
    """Blank out whole-line nginx comments, preserving line numbers.

    BACK-1102: N-rules that structurally match `server { ... }` / directive
    text via regex previously matched commented-out blocks the same as live
    ones -- a fully `#`-commented server{} (staged rollout, disabled legacy
    vhost) read as a live SSL server missing HSTS/cert/rate-limiting, or a
    single commented-out `# ssl_certificate ...;` line inside an otherwise
    live block still counted as "certificate present" (a false negative, the
    more dangerous direction). Call this on `content` and on any
    include/global file text before running structural or directive-presence
    regexes against it. Blanking (not deleting) each matched line keeps the
    newline count identical, so `content[:match.start()].count('\\n')`-style
    line-number math in callers is unaffected.
    """
    return _NGINX_COMMENT_LINE_RE.sub('', content)


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


def nginx_http_level_statements(source: str, base_path: str) -> Iterator[str]:
    """The directives set at http{} level in `source`, without their `;`: the direct
    children of each http{} block, then the top-level directives of each file one of
    them includes (resolved relative to `base_path`, one level deep). A directive inside
    a server{}, location{} or other nested block is not http-level, inline or included:
    reading the whole http{} text let one vhost's ssl_certificate in nginx.conf cover
    every other vhost (BACK-2280). An include that cannot be resolved (a glob, a
    missing file) or read is skipped: a global setting is never assumed.
    """
    for _header, body in find_blocks(source, 'http'):
        for statement in top_level_statements(body):
            yield statement
            words = statement.split(None, 1)
            if words[0] != 'include' or len(words) < 2:
                continue
            resolved = nginx_resolve_include(words[1].strip().strip('\'"'), base_path)
            if resolved is None:
                continue  # can't verify -- don't assume a global setting exists
            try:
                with open(resolved, encoding='utf-8', errors='replace') as fh:
                    included = fh.read()
            except (OSError, ValueError):
                continue  # unreadable -- don't assume a global setting exists
            yield from top_level_statements(included)


def nginx_http_level_has(source: str, base_path: str, pattern: 're.Pattern[str]') -> bool:
    """Return True if `pattern` matches a directive set at http{} level in `source`
    (`nginx_http_level_statements`), each read as written with its `;` (N002, N008,
    N009).
    """
    return any(pattern.search(statement + ';')
               for statement in nginx_http_level_statements(source, base_path))


def nginx_conf_http_level_has(file_path: str, pattern: 're.Pattern[str]') -> bool:
    """Return True if `pattern` is set at http{} level in the nginx.conf found for
    `file_path` (`nginx_find_nginx_conf`). False when no nginx.conf is found or it
    cannot be read: no suppression on uncertainty.
    """
    nginx_conf = nginx_find_nginx_conf(file_path)
    if nginx_conf is None:
        return False
    try:
        with open(nginx_conf, encoding='utf-8', errors='replace') as fh:
            conf_content = nginx_strip_comments(fh.read())
    except (OSError, ValueError):
        return False
    return nginx_http_level_has(conf_content, nginx_conf, pattern)
