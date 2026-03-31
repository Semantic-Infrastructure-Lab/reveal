"""Overview and summary generation for Claude sessions."""

import re
from typing import Dict, List, Any, Optional
from collections import defaultdict
from datetime import datetime

from .tools import calculate_tool_success_rate


_BOILERPLATE_PREFIXES = ('# Session Continuation Context',)


def _extract_text_from_content(content: Any) -> str:
    """Extract plain text from str or list-of-content-blocks content."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                return item.get('text', '').strip()
    return ''


def _extract_badge_from_messages(messages: List[Dict]) -> Optional[str]:
    """Extract session badge text from Bash tool calls (pattern: session badge "text")."""
    for msg in messages:
        if msg.get('type') != 'assistant':
            continue
        for block in msg.get('message', {}).get('content', []):
            if block.get('type') == 'tool_use' and block.get('name') == 'Bash':
                cmd = block.get('input', {}).get('command', '')
                m = re.search(r'session badge\s+"([^"]+)"', cmd)
                if m:
                    return m.group(1)
    return None


def _extract_session_title(messages: List[Dict]) -> Optional[str]:
    """Extract a display title from session messages.

    Priority:
      1. ``session badge "text"`` Bash call (most authoritative)
      2. First non-boilerplate user message first line
      3. None
    """
    # 1. Badge is the authoritative title when present
    badge = _extract_badge_from_messages(messages)
    if badge:
        return badge

    # 2. First real user message
    for msg in messages:
        if msg.get('type') != 'user':
            continue
        text = _extract_text_from_content(msg.get('message', {}).get('content', ''))
        if not text:
            continue
        candidate = text.split('\n')[0].strip()
        # Skip auto-injected boilerplate preambles
        if any(candidate.startswith(p) for p in _BOILERPLATE_PREFIXES):
            sep_idx = text.rfind('\n---\n')
            if sep_idx >= 0:
                candidate = text[sep_idx + 5:].strip().split('\n')[0].strip()
            else:
                continue
        # Skip bare boot commands
        if candidate.lower() == 'boot':
            continue
        if candidate:
            return candidate[:100]
    return None


def _measure_content_block(block: Dict[str, Any]) -> tuple:
    """Return (text_size, is_thinking) for one assistant content block."""
    if block.get('type') == 'text':
        return len(block.get('text', '')), False
    if block.get('type') == 'thinking':
        return len(block.get('thinking', '')), True
    return 0, False


def analyze_message_sizes(messages: List[Dict]) -> Dict[str, Any]:
    """Analyze message size distribution.

    Args:
        messages: List of message dictionaries

    Returns:
        Dictionary with average, max, and thinking block count
    """
    sizes = []
    thinking_blocks = 0

    for msg in messages:
        if msg.get('type') != 'assistant':
            continue
        msg_size = 0
        for content in msg.get('message', {}).get('content', []):
            size, is_thinking = _measure_content_block(content)
            msg_size += size
            if is_thinking:
                thinking_blocks += 1
        sizes.append(msg_size)

    return {
        'avg': sum(sizes) // len(sizes) if sizes else 0,
        'max': max(sizes) if sizes else 0,
        'thinking_blocks': thinking_blocks
    }


def _calculate_session_duration(messages: List[Dict]) -> Any:
    """Calculate session duration from message timestamps."""
    timestamps = [ts for ts in (msg.get('timestamp') for msg in messages) if ts]
    if len(timestamps) >= 2:
        try:
            start = datetime.fromisoformat(timestamps[0].replace('Z', '+00:00'))
            end = datetime.fromisoformat(timestamps[-1].replace('Z', '+00:00'))
            total_seconds = int((end - start).total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            return f"{minutes}m {seconds}s"
        except (ValueError, AttributeError):
            pass
    return None


def _collect_files_touched(messages: List[Dict]) -> List[str]:
    """Collect distinct file paths from Edit/Write/Read tool calls, in order of first appearance."""
    seen: Dict[str, int] = {}
    file_tools = {'Edit', 'Write', 'Read'}
    for msg in messages:
        if msg.get('type') != 'assistant':
            continue
        for block in msg.get('message', {}).get('content', []):
            if block.get('type') == 'tool_use' and block.get('name') in file_tools:
                path = block.get('input', {}).get('file_path', '')
                if path and path not in seen:
                    seen[path] = len(seen)
    return sorted(seen.keys(), key=lambda p: seen[p])


def _get_last_assistant_snippet(messages: List[Dict]) -> Optional[str]:
    """Return the last 100 chars of the last assistant text block."""
    for msg in reversed(messages):
        if msg.get('type') != 'assistant':
            continue
        for block in reversed(msg.get('message', {}).get('content', [])):
            if block.get('type') == 'text':
                text = block.get('text', '').strip()
                if text:
                    snippet = text[:100]
                    if len(text) > 100:
                        snippet += '…'
                    return snippet
    return None


def _collect_token_usage(messages: List[Dict]) -> Dict[str, Any]:
    """Sum token usage across all complete assistant messages.

    Only counts messages with stop_reason set (not None) to avoid double-counting
    streaming intermediates. Returns zeroed dict when no usage data is found.
    """
    totals = {
        'input_tokens': 0,
        'output_tokens': 0,
        'cache_read_tokens': 0,
        'cache_created_tokens': 0,
        'messages_with_usage': 0,
    }
    for msg in messages:
        if msg.get('type') != 'assistant':
            continue
        m = msg.get('message', {})
        if m.get('stop_reason') is None:
            continue  # streaming intermediate — skip to avoid double-counting
        usage = m.get('usage')
        if not isinstance(usage, dict):
            continue
        totals['input_tokens'] += usage.get('input_tokens', 0)
        totals['output_tokens'] += usage.get('output_tokens', 0)
        totals['cache_read_tokens'] += usage.get('cache_read_input_tokens', 0)
        totals['cache_created_tokens'] += usage.get('cache_creation_input_tokens', 0)
        totals['messages_with_usage'] += 1
    total_input = totals['input_tokens'] + totals['cache_read_tokens'] + totals['cache_created_tokens']
    if total_input > 0:
        hit_pct = round(totals['cache_read_tokens'] / total_input * 100)
        totals['cache_hit_rate'] = f"{hit_pct}%"
    else:
        totals['cache_hit_rate'] = '0%'
    return totals


def _collect_context(messages: List[Dict]) -> Optional[Dict[str, Any]]:
    """Extract cwd, git_branch, and version from the first assistant message."""
    for msg in messages:
        if msg.get('type') != 'assistant':
            continue
        ctx: Dict[str, Any] = {}
        if msg.get('cwd'):
            ctx['cwd'] = msg['cwd']
        if msg.get('gitBranch'):
            ctx['git_branch'] = msg['gitBranch']
        if msg.get('version'):
            ctx['version'] = msg['version']
        return ctx if ctx else None
    return None


def _check_readme_present(conversation_path: str) -> bool:
    """Check if README*.md exists in the session directory (parent of conversation file)."""
    try:
        from pathlib import Path as _Path
        session_dir = _Path(conversation_path).parent
        return any(session_dir.glob('README*.md'))
    except Exception:
        return False


def _process_content_list(
    content_list: List[Dict], tools_used: Dict, file_operations: Dict
) -> int:
    """Process assistant content blocks; return total thinking chars accumulated."""
    _file_ops = {'Read', 'Write', 'Edit'}
    thinking_chars = 0
    for content in content_list:
        ctype = content.get('type')
        if ctype == 'tool_use':
            tool_name = content.get('name')
            tools_used[tool_name] += 1
            if tool_name in _file_ops:
                file_operations[tool_name] += 1
        elif ctype == 'thinking':
            thinking_chars += len(content.get('thinking', ''))
    return thinking_chars


def _collect_message_stats(messages: List[Dict]) -> Dict[str, Any]:
    """Collect tool usage, file operations, and thinking stats from messages."""
    tools_used: Dict[str, int] = defaultdict(int)
    thinking_chars = 0
    user_messages = 0
    assistant_messages = 0
    file_operations: Dict[str, int] = defaultdict(int)

    for msg in messages:
        msg_type = msg.get('type')
        if msg_type == 'user':
            user_messages += 1
        elif msg_type == 'assistant':
            assistant_messages += 1
            thinking_chars += _process_content_list(
                msg.get('message', {}).get('content', []), tools_used, file_operations
            )

    return {
        'tools_used': dict(tools_used),
        'thinking_chars': thinking_chars,
        'user_messages': user_messages,
        'assistant_messages': assistant_messages,
        'file_operations': dict(file_operations),
    }


def get_overview(messages: List[Dict], session_name: str, conversation_path: str,
                 contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Generate session overview with key metrics.

    Args:
        messages: List of message dictionaries
        session_name: Name of the session
        conversation_path: Path to conversation file
        contract_base: Base contract fields

    Returns:
        Overview dictionary with:
        - Message counts
        - Tool usage statistics
        - File operations
        - Thinking token estimates
        - Session duration
    """
    base = contract_base.copy()
    base['type'] = 'claude_session_overview'

    stats = _collect_message_stats(messages)
    duration = _calculate_session_duration(messages)
    title = _extract_session_title(messages)

    files_touched = _collect_files_touched(messages)
    last_snippet = _get_last_assistant_snippet(messages)
    readme_present = _check_readme_present(conversation_path)
    token_summary = _collect_token_usage(messages)
    context = _collect_context(messages)

    base.update({
        'session': session_name,
        'title': title,
        'message_count': len(messages),
        'user_messages': stats['user_messages'],
        'assistant_messages': stats['assistant_messages'],
        'tools_used': stats['tools_used'],
        'file_operations': stats['file_operations'],
        'thinking_chars_approx': stats['thinking_chars'],
        'thinking_tokens_approx': stats['thinking_chars'] // 4,  # Rough estimate
        'duration': duration,
        'files_touched': files_touched,
        'files_touched_count': len(files_touched),
        'readme_present': readme_present,
        'last_assistant_snippet': last_snippet,
        'conversation_file': conversation_path,
        'token_summary': token_summary,
    })
    if context:
        base['context'] = context

    return base


def get_summary(messages: List[Dict], session_name: str, conversation_path: str,
                contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Generate detailed analytics summary.

    Args:
        messages: List of message dictionaries
        session_name: Name of the session
        conversation_path: Path to conversation file
        contract_base: Base contract fields

    Returns:
        Summary with detailed analytics (tool success rates, message sizes, etc.)
    """
    overview = get_overview(messages, session_name, conversation_path, contract_base)
    overview['type'] = 'claude_analytics'

    # Add detailed analytics
    tool_success_rate = calculate_tool_success_rate(messages)
    message_sizes = analyze_message_sizes(messages)

    overview.update({
        'tool_success_rate': tool_success_rate,
        'avg_message_size': message_sizes['avg'],
        'max_message_size': message_sizes['max'],
        'thinking_blocks': message_sizes['thinking_blocks']
    })

    return overview


def get_context_changes(messages: List[Dict], session_name: str,
                        contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Track working directory and git branch changes during session.

    Args:
        messages: List of message dictionaries
        session_name: Name of the session
        contract_base: Base contract fields

    Returns:
        Dictionary with directory and branch change history
    """
    base = contract_base.copy()
    base['type'] = 'claude_context'

    changes = []
    prev_cwd = None
    prev_branch = None

    for i, msg in enumerate(messages):
        cwd = msg.get('cwd')
        branch = msg.get('gitBranch')

        # Track directory changes
        if cwd and cwd != prev_cwd:
            changes.append({
                'message_index': i,
                'type': 'cwd',
                'value': cwd,
                'timestamp': msg.get('timestamp')
            })
            prev_cwd = cwd

        # Track branch changes
        if branch and branch != prev_branch:
            changes.append({
                'message_index': i,
                'type': 'branch',
                'value': branch,
                'timestamp': msg.get('timestamp')
            })
            prev_branch = branch

    base.update({
        'session': session_name,
        'total_changes': len(changes),
        'final_cwd': prev_cwd,
        'final_branch': prev_branch,
        'changes': changes
    })

    return base


def get_token_breakdown(messages: List[Dict], session_name: str,
                        contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Per-message token breakdown showing context growth over the session.

    Route: claude://session/NAME?tokens

    Each entry covers one complete assistant turn (stop_reason != None).
    cumulative_input tracks total input context growth across turns.

    Args:
        messages: List of message dictionaries
        session_name: Name of the session
        contract_base: Base contract fields

    Returns:
        claude_token_breakdown dict with per-message entries and session totals
    """
    base = contract_base.copy()
    base['type'] = 'claude_token_breakdown'

    entries = []
    totals = {
        'input_tokens': 0,
        'output_tokens': 0,
        'cache_read_tokens': 0,
        'cache_created_tokens': 0,
    }
    cumulative_input = 0

    for i, msg in enumerate(messages):
        if msg.get('type') != 'assistant':
            continue
        m = msg.get('message', {})
        if m.get('stop_reason') is None:
            continue
        usage = m.get('usage')
        if not isinstance(usage, dict):
            continue

        inp = usage.get('input_tokens', 0)
        out = usage.get('output_tokens', 0)
        cache_read = usage.get('cache_read_input_tokens', 0)
        cache_created = usage.get('cache_creation_input_tokens', 0)
        cumulative_input += inp + cache_read + cache_created

        entries.append({
            'message_index': i,
            'timestamp': msg.get('timestamp'),
            'input_tokens': inp,
            'output_tokens': out,
            'cache_read_tokens': cache_read,
            'cache_created_tokens': cache_created,
            'cumulative_input': cumulative_input,
        })

        totals['input_tokens'] += inp
        totals['output_tokens'] += out
        totals['cache_read_tokens'] += cache_read
        totals['cache_created_tokens'] += cache_created

    total_input = totals['input_tokens'] + totals['cache_read_tokens'] + totals['cache_created_tokens']
    hit_pct = round(totals['cache_read_tokens'] / total_input * 100) if total_input > 0 else 0
    totals['cache_hit_rate'] = f"{hit_pct}%"

    base.update({
        'session': session_name,
        'messages': entries,
        'totals': totals,
    })
    return base
