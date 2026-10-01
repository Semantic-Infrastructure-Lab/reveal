"""Recognizing secret values, for views that print a user's configuration.

``KNOWN_SECRET_PREFIXES`` is the one list of credential formats: the S001 rule flags them in
code, and :func:`redact_secrets` masks them in configuration an adapter prints (codex://config).

Masking only by key name let a credential through wherever its key looked innocent. Measured on
a codex config with eight fake secrets, four printed in full: a token passed as an MCP server
argument (``args = ["--token", "ghp_..."]`` and ``"--api-key=sk-..."``), ``ANTHROPIC_KEY``, and
the password inside ``DATABASE_URL``.
"""

import re
from typing import Any

# Value prefixes that are unambiguously real secrets
KNOWN_SECRET_PREFIXES = (
    'sk-proj-', 'sk-ant-', 'sk-',   # Anthropic / OpenAI
    'ghp_', 'ghs_', 'gho_',          # GitHub tokens
    'AKIA', 'ASIA',                   # AWS access keys
    'xoxb-', 'xoxp-', 'xoxa-',       # Slack tokens
    'eyJ',                            # JWT (base64 header)
    'glpat-',                         # GitLab PAT
    'npm_',                           # npm tokens
    'ya29.',                          # Google OAuth
)

# A key or flag name that holds a secret: a substring (api_key, x-auth-token, Authorization),
# or KEY / PAT as a whole word (ANTHROPIC_KEY, X-Api-Key, GITLAB_PAT -- not 'keyboard').
_SECRET_NAME = re.compile(
    r'api.?key|secret|token|passw|credential|auth|bearer|private.?key|access.?key'
    r'|(?:^|[_\-.])(?:key|pat)(?:$|[_\-.])',
    re.IGNORECASE,
)

# A known-format token anywhere in a string, as a whole token (not the 'sk-' in 'task-list').
_TOKEN_IN_TEXT = re.compile(
    r'(?<![A-Za-z0-9])(?:' + '|'.join(re.escape(p) for p in KNOWN_SECRET_PREFIXES) +
    r')[A-Za-z0-9_\-./+=]{6,}'
)

# The password of URL credentials: scheme://user:PASSWORD@host
_URL_PASSWORD = re.compile(r'(?P<head>[a-z][a-z0-9+.\-]*://[^:/@\s]+:)[^@\s]+(?=@)', re.IGNORECASE)

_FLAG = re.compile(r'^--?(?P<name>[A-Za-z0-9_\-]+)(?:=(?P<value>.*))?$', re.DOTALL)


def is_secret_name(name: str) -> bool:
    return bool(_SECRET_NAME.search(name))


def mask(value: str) -> str:
    """Keep a short prefix so the reader can tell which credential it is."""
    return value[:4] + '***' if len(value) > 8 else '***'


def _redact_text(text: str) -> str:
    text = _TOKEN_IN_TEXT.sub(lambda m: mask(m.group(0)), text)
    return _URL_PASSWORD.sub(lambda m: m.group('head') + '***', text)


def _redact_list(items: list) -> list:
    out: list = []
    mask_next = False
    for item in items:
        if mask_next and isinstance(item, str):
            out.append(mask(item))
            mask_next = False
            continue
        mask_next = False
        if isinstance(item, str):
            flag = _FLAG.match(item)
            if flag and is_secret_name(flag.group('name')):
                if flag.group('value') is None:
                    mask_next = True          # --token VALUE
                    out.append(item)
                else:                         # --token=VALUE
                    out.append(item[: len(item) - len(flag.group('value'))] + mask(flag.group('value')))
                continue
        out.append(redact_secrets(item))
    return out


def redact_secrets(obj: Any) -> Any:
    """*obj* (parsed config) with every recognizable secret masked, at any depth.

    A string is masked whole when its key names a secret, and otherwise has any known-format
    token or URL password inside it masked. In a list, the value after a secret-named flag
    (``--token X``, ``--api-key=X``) is masked too.
    """
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if isinstance(value, str) and is_secret_name(str(key)):
                result[key] = mask(value)
            else:
                result[key] = redact_secrets(value)
        return result
    if isinstance(obj, list):
        return _redact_list(obj)
    if isinstance(obj, str):
        return _redact_text(obj)
    return obj
