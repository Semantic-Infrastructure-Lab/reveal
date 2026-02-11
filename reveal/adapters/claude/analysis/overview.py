"""Overview and summary generation for Claude sessions."""

from typing import Dict, List, Any
from collections import defaultdict
from datetime import datetime

from .tools import calculate_tool_success_rate


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
        if msg.get('type') == 'assistant':
            msg_size = 0
            for content in msg.get('message', {}).get('content', []):
                if content.get('type') == 'text':
                    msg_size += len(content.get('text', ''))
                elif content.get('type') == 'thinking':
                    msg_size += len(content.get('thinking', ''))
                    thinking_blocks += 1
            sizes.append(msg_size)

    return {
        'avg': sum(sizes) // len(sizes) if sizes else 0,
        'max': max(sizes) if sizes else 0,
        'thinking_blocks': thinking_blocks
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

            # Parse content blocks
            for content in msg.get('message', {}).get('content', []):
                if content.get('type') == 'tool_use':
                    tool_name = content.get('name')
                    tools_used[tool_name] += 1

                    # Track file operations
                    if tool_name in ('Read', 'Write', 'Edit'):
                        file_operations[tool_name] += 1

                elif content.get('type') == 'thinking':
                    thinking_chars += len(content.get('thinking', ''))

    # Calculate duration
    timestamps = [msg.get('timestamp') for msg in messages if msg.get('timestamp')]
    duration = None
    if len(timestamps) >= 2:
        try:
            start = datetime.fromisoformat(timestamps[0].replace('Z', '+00:00'))
            end = datetime.fromisoformat(timestamps[-1].replace('Z', '+00:00'))
            duration = str(end - start)
        except (ValueError, AttributeError):
            pass

    base.update({
        'session': session_name,
        'message_count': len(messages),
        'user_messages': user_messages,
        'assistant_messages': assistant_messages,
        'tools_used': dict(tools_used),
        'file_operations': dict(file_operations),
        'thinking_chars_approx': thinking_chars,
        'thinking_tokens_approx': thinking_chars // 4,  # Rough estimate
        'duration': duration,
        'conversation_file': conversation_path
    })

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
