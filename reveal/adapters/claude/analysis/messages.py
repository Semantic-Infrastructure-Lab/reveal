"""Message filtering and extraction for Claude sessions."""

import re
from typing import Dict, List, Any, Optional


def _extract_text(content) -> str:
    """Normalize content to plain text, regardless of format.

    Handles the two formats seen in Claude Code JSONL:
    - str: initial user message stored as raw string
    - list[dict]: structured content blocks (text, thinking, tool_use, tool_result)

    Returns extracted text only (skips thinking/tool_use/tool_result).
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ''
    parts = []
    for block in content:
        try:
            if isinstance(block, dict) and block.get('type') == 'text':
                parts.append(block.get('text', ''))
        except Exception:
            continue
    return '\n'.join(parts)


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


def filter_by_role(messages: List[Dict], role: str, session_name: str,
                   contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Filter messages by role (user or assistant).

    Args:
        messages: List of message dictionaries
        role: Role to filter ('user' or 'assistant')
        session_name: Name of the session
        contract_base: Base contract fields

    Returns:
        Dictionary with filtered messages, content normalized to list of blocks
    """
    base = contract_base.copy()
    base['type'] = f'claude_{role}_messages'

    filtered = []

    for i, msg in enumerate(messages):
        if msg.get('type') == role:
            raw_content = msg.get('message', {}).get('content', [])
            filtered.append({
                'message_index': i,
                'timestamp': msg.get('timestamp'),
                'content': _content_to_blocks(raw_content),
            })

    base.update({
        'session': session_name,
        'role': role,
        'message_count': len(filtered),
        'messages': filtered
    })

    return base


def get_message(messages: List[Dict], msg_id: int, session_name: str,
                contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Get specific message by index.

    Args:
        messages: List of message dictionaries
        msg_id: Message index (0-based)
        session_name: Name of the session
        contract_base: Base contract fields

    Returns:
        Dictionary with message details
    """
    base = contract_base.copy()
    base['type'] = 'claude_message'

    if msg_id < 0 or msg_id >= len(messages):
        base.update({
            'session': session_name,
            'error': f'Message index {msg_id} out of range (0-{len(messages)-1})'
        })
        return base

    msg = messages[msg_id]
    raw_content = msg.get('message', {}).get('content', [])
    msg_type = msg.get('type')

    result: Dict[str, Any] = {
        'session': session_name,
        'message_index': msg_id,
        'timestamp': msg.get('timestamp'),
        'message_type': msg_type,
        'message': msg.get('message', {}),
        'text': _extract_text(raw_content),
    }

    # Help users understand metadata records that are not conversation messages
    if msg_type == 'file-history-snapshot':
        result['hint'] = (
            'This is a Claude Code metadata record, not a conversation message. '
            'Use /user or /assistant to browse real messages, '
            'or /message/2 to jump to the first user prompt.'
        )

    base.update(result)
    return base


def _iter_thinking_blocks(content: list, msg_index: int, timestamp: Any):
    """Yield thinking block dicts from one message's content list."""
    for block in content:
        try:
            if isinstance(block, dict) and block.get('type') == 'thinking':
                thinking = block.get('thinking', '')
                yield {
                    'message_index': msg_index,
                    'content': thinking,
                    'char_count': len(thinking),
                    'token_estimate': len(thinking) // 4,
                    'timestamp': timestamp,
                }
        except Exception:
            continue


def get_thinking_blocks(messages: List[Dict], session_name: str,
                        contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Extract all thinking blocks.

    Args:
        messages: List of message dictionaries
        session_name: Name of the session
        contract_base: Base contract fields

    Returns:
        Dictionary with thinking block count and list of blocks with content
    """
    base = contract_base.copy()
    base['type'] = 'claude_thinking'

    thinking_blocks = []

    for i, msg in enumerate(messages):
        if msg.get('type') == 'assistant':
            content = msg.get('message', {}).get('content', [])
            if not isinstance(content, list):
                continue
            thinking_blocks.extend(_iter_thinking_blocks(content, i, msg.get('timestamp')))

    base.update({
        'session': session_name,
        'thinking_block_count': len(thinking_blocks),
        'total_chars': sum(b['char_count'] for b in thinking_blocks),
        'total_tokens_estimate': sum(b['token_estimate'] for b in thinking_blocks),
        'blocks': thinking_blocks
    })

    return base


def _matches_term(text: str, lower_term: str, whole_word: bool) -> bool:
    """Return True if text contains lower_term, respecting whole_word flag."""
    if whole_word:
        return bool(re.search(r'\b' + re.escape(lower_term) + r'\b', text, re.IGNORECASE))
    return lower_term in text.lower()


def _search_block(block: Dict, lower_term: str, term: str, i: int, role: str, ts: str,
                  whole_word: bool = False):
    """Search a single content block for the term. Returns a match dict or None."""
    if not isinstance(block, dict):
        return None
    btype = block.get('type', '')
    if btype == 'text':
        text = block.get('text', '')
        if _matches_term(text, lower_term, whole_word):
            return {'message_index': i, 'role': role, 'block_type': 'text',
                    'timestamp': ts, 'excerpt': _find_excerpt(text, term)}
    elif btype == 'thinking':
        text = block.get('thinking', '')
        if _matches_term(text, lower_term, whole_word):
            return {'message_index': i, 'role': role, 'block_type': 'thinking',
                    'timestamp': ts, 'excerpt': _find_excerpt(text, term)}
    elif btype == 'tool_use':
        inp = block.get('input', {})
        searchable = ' '.join(str(v) for v in inp.values() if isinstance(v, str))
        name = block.get('name', '')
        if _matches_term(searchable, lower_term, whole_word) or _matches_term(name, lower_term, whole_word):
            return {'message_index': i, 'role': role, 'block_type': f'tool_use:{name}',
                    'timestamp': ts, 'excerpt': _find_excerpt(searchable or name, term, window=80)}
    elif btype == 'tool_result':
        content = block.get('content', '')
        if isinstance(content, list):
            text = ' '.join(b.get('text', '') for b in content
                            if isinstance(b, dict) and b.get('type') == 'text')
        else:
            text = str(content) if content else ''
        if text and _matches_term(text, lower_term, whole_word):
            return {'message_index': i, 'role': role, 'block_type': 'tool_result',
                    'timestamp': ts, 'excerpt': _find_excerpt(text, term)}
    return None


def _extract_text_parts(content: list) -> List[str]:
    """Return non-empty text strings from a list of content blocks."""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get('type') == 'text':
            t = block.get('text', '').strip()
            if t:
                parts.append(t)
    return parts


def _collect_block_matches(
    blocks: list, lower_term: str, term: str, msg_index: int, role: str, ts: str,
    whole_word: bool = False,
) -> list:
    """Search all blocks for term and return list of match dicts."""
    matches = []
    for block in blocks:
        try:
            match = _search_block(block, lower_term, term, msg_index, role, ts, whole_word=whole_word)
            if match:
                matches.append(match)
        except Exception:
            continue
    return matches


def search_messages(messages: List[Dict], term: str, session_name: str,
                    contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Search all message content for a term (case-insensitive).

    Searches text blocks, thinking blocks, and tool descriptions.

    Args:
        messages: List of message dictionaries
        term: Search term (case-insensitive substring match)
        session_name: Name of the session
        contract_base: Base contract fields

    Returns:
        Dictionary with matching messages and excerpts
    """
    base = contract_base.copy()
    base['type'] = 'claude_search_results'

    lower_term = term.lower()
    matches = []

    for i, msg in enumerate(messages):
        role = msg.get('type', '')
        if role not in ('user', 'assistant'):
            continue

        blocks = _content_to_blocks(msg.get('message', {}).get('content', []))
        ts = (msg.get('timestamp') or '')[:16].replace('T', ' ')

        matches.extend(_collect_block_matches(blocks, lower_term, term, i, role, ts))

    base.update({
        'session': session_name,
        'term': term,
        'match_count': len(matches),
        'matches': matches,
    })

    return base


def get_messages(messages: List[Dict], session_name: str,
                 contract_base: Dict[str, Any],
                 search: Optional[str] = None) -> Dict[str, Any]:
    """Extract assistant narrative text turns (not tool calls).

    Returns what the assistant *said* — explanations, summaries, decisions —
    not tool use records. Useful for understanding what Peyton/Claude was
    thinking and communicating, not just what it did.

    Args:
        messages: List of message dictionaries
        session_name: Name of the session
        contract_base: Base contract fields
        search: Optional search term to filter messages containing it

    Returns:
        Dictionary with assistant messages list
    """
    base = contract_base.copy()
    base['type'] = 'claude_messages'

    lower_search = search.lower() if search else None
    turns: List[Dict[str, Any]] = []

    for i, msg in enumerate(messages):
        if msg.get('type') != 'assistant':
            continue

        content = msg.get('message', {}).get('content', [])
        if not isinstance(content, list):
            continue

        # Collect only text blocks (skip tool_use, tool_result, thinking)
        text_parts = _extract_text_parts(content)

        if not text_parts:
            continue

        text = '\n\n'.join(text_parts)

        if lower_search and lower_search not in text.lower():
            continue

        ts = (msg.get('timestamp') or '')[:16].replace('T', ' ')
        turns.append({
            'turn': len(turns) + 1,
            'message_index': i,
            'timestamp': ts,
            'text': text,
            'char_count': len(text),
        })

    base.update({
        'session': session_name,
        'total_turns': len(turns),
        'messages': turns,
    })
    if search:
        base['search'] = search

    return base


def get_message_range(messages: List[Dict], session_name: str,
                      contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Return interleaved user+assistant messages for range slicing.

    Filters out metadata records (file-history-snapshot, etc.) and returns
    only conversation messages. Range slicing is applied by
    _post_process_message_range via _slice_list after this returns.

    Each entry includes raw message_index so callers can drill in with
    /message/N after finding a message of interest.
    """
    base = contract_base.copy()
    base['type'] = 'claude_message_range'

    items: List[Dict[str, Any]] = []
    for i, msg in enumerate(messages):
        role = msg.get('type', '')
        if role not in ('user', 'assistant'):
            continue
        raw_content = msg.get('message', {}).get('content', [])
        ts = (msg.get('timestamp') or '')[:16].replace('T', ' ')
        items.append({
            'turn': len(items) + 1,
            'message_index': i,
            'role': role,
            'timestamp': ts,
            'content': raw_content if isinstance(raw_content, list) else [],
        })

    base.update({
        'session': session_name,
        'total_messages': len(items),
        'messages': items,
    })
    return base


def _find_excerpt(text: str, term: str, window: int = 120) -> str:
    """Return a short excerpt around the first occurrence of term."""
    lower = text.lower()
    pos = lower.find(term.lower())
    if pos == -1:
        return text[:window]
    start = max(0, pos - window // 3)
    end = min(len(text), pos + len(term) + (window * 2 // 3))
    excerpt = text[start:end].strip()
    if start > 0:
        excerpt = '...' + excerpt
    if end < len(text):
        excerpt = excerpt + '...'
    return excerpt
