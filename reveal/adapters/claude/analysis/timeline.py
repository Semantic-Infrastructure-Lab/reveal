"""Timeline generation for Claude sessions."""

from typing import Dict, List, Any


def _create_tool_result_event(i: int, timestamp: str, content: Dict) -> Dict[str, Any]:
    """Create a tool result timeline event.

    Args:
        i: Message index
        timestamp: Event timestamp
        content: Tool result content block

    Returns:
        Timeline event dictionary
    """
    is_error = content.get('is_error', False)
    result_content = str(content.get('content', ''))
    has_error = is_error or 'error' in result_content.lower()

    return {
        'index': i,
        'timestamp': timestamp,
        'event_type': 'tool_result',
        'tool_id': content.get('tool_use_id'),
        'status': 'error' if has_error else 'success',
        'content_preview': result_content[:100]
    }


def _process_user_message(i: int, timestamp: str, content_blocks: List) -> List[Dict[str, Any]]:
    """Process user message content blocks into timeline events.

    Args:
        i: Message index
        timestamp: Event timestamp
        content_blocks: List of content blocks from user message

    Returns:
        List of timeline events
    """
    events = []

    # User text messages
    text_parts = [c.get('text', '') for c in content_blocks
                  if isinstance(c, dict) and c.get('type') == 'text']
    text = ' '.join(text_parts)
    if text:
        events.append({
            'index': i,
            'timestamp': timestamp,
            'event_type': 'user_message',
            'content_preview': text[:100]
        })

    # Tool results (returned from tool execution)
    for content in content_blocks:
        if isinstance(content, dict) and content.get('type') == 'tool_result':
            events.append(_create_tool_result_event(i, timestamp, content))

    return events


def _process_assistant_message(
        i: int, timestamp: str, content_blocks: List) -> List[Dict[str, Any]]:
    """Process assistant message content blocks into timeline events.

    Args:
        i: Message index
        timestamp: Event timestamp
        content_blocks: List of content blocks from assistant message

    Returns:
        List of timeline events
    """
    events = []

    for content in content_blocks:
        content_type = content.get('type')

        if content_type == 'text':
            text = content.get('text', '')
            if text:
                events.append({
                    'index': i,
                    'timestamp': timestamp,
                    'event_type': 'assistant_message',
                    'content_preview': text[:100]
                })

        elif content_type == 'tool_use':
            events.append({
                'index': i,
                'timestamp': timestamp,
                'event_type': 'tool_call',
                'tool_name': content.get('name'),
                'tool_id': content.get('id')
            })

        elif content_type == 'tool_result':
            events.append(_create_tool_result_event(i, timestamp, content))

        elif content_type == 'thinking':
            thinking_text = content.get('thinking', '')
            events.append({
                'index': i,
                'timestamp': timestamp,
                'event_type': 'thinking',
                'tokens_approx': len(thinking_text) // 4,
                'content_preview': thinking_text[:100]
            })

    return events


def get_timeline(messages: List[Dict], session_name: str,
                 contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Generate chronological timeline of conversation.

    Args:
        messages: List of message dictionaries
        session_name: Name of the session
        contract_base: Base contract fields

    Returns:
        Dictionary with timeline events (user messages, tool calls, tool results)
    """
    base = contract_base.copy()
    base['type'] = 'claude_timeline'

    timeline = []
    for i, msg in enumerate(messages):
        timestamp = msg.get('timestamp', 'Unknown')
        msg_type = msg.get('type')
        content_blocks = msg.get('message', {}).get('content', [])

        if msg_type == 'user':
            timeline.extend(_process_user_message(i, timestamp, content_blocks))
        elif msg_type == 'assistant':
            timeline.extend(_process_assistant_message(i, timestamp, content_blocks))

    base.update({
        'session': session_name,
        'event_count': len(timeline),
        'timeline': timeline
    })

    return base
