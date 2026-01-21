"""Message filtering and extraction for Claude sessions."""

from typing import Dict, List, Any


def filter_by_role(messages: List[Dict], role: str, session_name: str,
                   contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Filter messages by role (user or assistant).

    Args:
        messages: List of message dictionaries
        role: Role to filter ('user' or 'assistant')
        session_name: Name of the session
        contract_base: Base contract fields

    Returns:
        Dictionary with filtered messages
    """
    base = contract_base.copy()
    base['type'] = f'claude_{role}_messages'

    filtered = []

    for i, msg in enumerate(messages):
        if msg.get('type') == role:
            filtered.append({
                'message_index': i,
                'timestamp': msg.get('timestamp'),
                'content': msg.get('message', {}).get('content', [])
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

    base.update({
        'session': session_name,
        'message_index': msg_id,
        'timestamp': msg.get('timestamp'),
        'message_type': msg.get('type'),  # Changed from 'type' to 'message_type'
        'message': msg.get('message', {})
    })

    return base


def get_thinking_blocks(messages: List[Dict], session_name: str,
                        contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Extract all thinking blocks.

    Args:
        messages: List of message dictionaries
        session_name: Name of the session
        contract_base: Base contract fields

    Returns:
        Dictionary with thinking block count and list of blocks
    """
    base = contract_base.copy()
    base['type'] = 'claude_thinking'

    thinking_blocks = []

    for i, msg in enumerate(messages):
        if msg.get('type') == 'assistant':
            for content in msg.get('message', {}).get('content', []):
                if content.get('type') == 'thinking':
                    thinking = content.get('thinking', '')
                    thinking_blocks.append({
                        'message_index': i,
                        'content': thinking,
                        'char_count': len(thinking),
                        'token_estimate': len(thinking) // 4,
                        'timestamp': msg.get('timestamp')
                    })

    base.update({
        'session': session_name,
        'thinking_block_count': len(thinking_blocks),
        'total_chars': sum(b['char_count'] for b in thinking_blocks),
        'total_tokens_estimate': sum(b['token_estimate'] for b in thinking_blocks),
        'blocks': thinking_blocks
    })

    return base
