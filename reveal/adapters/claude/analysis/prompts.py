"""What counts as a human-typed prompt in a Claude Code transcript (shared by messages, overview, timeline)."""

import re
from typing import Dict


def _content_to_blocks(content) -> list:
    """Normalize content to a list of structured blocks.

    Converts string content to a single text block so callers
    always get a list, never a bare string.
    """
    if isinstance(content, str):
        return [{'type': 'text', 'text': content}]
    if isinstance(content, list):
        return content
    return []


# Synthetic system-injected text: task-notification bodies (async Agent-tool
# completions) and bash-mode (`!command`) wrappers. A whitelist, not the generic
# "^<[a-z]" tag-prefix convention handlers/sessions.py uses for title extraction —
# that broader pattern also matches real pasted HTML/XML (<p>, <script>, <html>, ...)
# confirmed present as genuine human prompts in real sessions, so a generic prefix
# check here would silently drop real prompts. Only exclude tag names confirmed
# harness-injected, never something a human would plausibly type as their first word.
_SYNTHETIC_PREFIX_RE = re.compile(
    r'^<(task-notification|local-command-caveat|local-command-stdout|'
    r'local-command-stderr|command-name|command-message|bash-input|bash-stdout|bash-stderr)>'
)


def _is_real_prompt(msg: Dict) -> bool:
    """True if a user-role message is real human-typed text, not a tool-result wrap.

    Content shapes seen in Claude Code JSONL for role: user:
    - bare str: the common case for a typed prompt
    - list with a text block (optionally alongside an image block, e.g. a pasted
      screenshot with a caption): also a real prompt — NOT covered by a bare
      isinstance(content, str) check, confirmed present in real sessions
    - list with a text block alongside a tool_result block: synthetic system text
      (e.g. "Tool loaded.") riding on a tool-result turn, not human-typed — excluded
    - text block whose content is a harness-injected wrapper (task-notification,
      bash-mode caveats/command echoes) rather than something the human typed —
      excluded via _SYNTHETIC_PREFIX_RE (confirmed on real sessions: async Agent-tool
      completions land as type=user/content=str, indistinguishable from a real prompt
      without this check — ~30% of "prompts" in Agent-heavy sessions before this fix)
    - records the harness marks itself: isMeta (local-command caveats, pasted-image
      source notes, skill bodies) and isCompactSummary (the summary that opens a
      compacted session) — checked over 10,021 local sessions, where they were
      ~2.2K false prompts, and bash-mode output (<bash-stdout>) another ~4.1K
    """
    if msg.get('type') != 'user' or msg.get('isMeta') or msg.get('isCompactSummary'):
        return False
    blocks = _content_to_blocks(msg.get('message', {}).get('content', []))
    types = {b.get('type') for b in blocks if isinstance(b, dict)}
    if 'text' not in types or 'tool_result' in types:
        return False
    text_block = next((b for b in blocks if isinstance(b, dict) and b.get('type') == 'text'), None)
    text = (text_block or {}).get('text', '')
    if _SYNTHETIC_PREFIX_RE.match(text.lstrip()):
        return False
    return True
