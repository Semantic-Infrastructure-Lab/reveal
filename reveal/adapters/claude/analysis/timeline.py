"""Timeline generation for Claude sessions."""

from typing import Dict, List, Any


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

        if msg_type == 'user':
            # Extract user message text and tool results
            content_blocks = msg.get('message', {}).get('content', [])

            # User text messages
            text_parts = [c.get('text', '') for c in content_blocks
                          if isinstance(c, dict) and c.get('type') == 'text']
            text = ' '.join(text_parts)
            if text:
                timeline.append({
                    'index': i,
                    'timestamp': timestamp,
                    'event_type': 'user_message',
                    'content_preview': text[:100]
                })

            # Tool results (returned from tool execution)
            for content in content_blocks:
                if isinstance(content, dict) and content.get('type') == 'tool_result':
                    is_error = content.get('is_error', False)
                    result_content = str(content.get('content', ''))
                    has_error = is_error or 'error' in result_content.lower()

                    timeline.append({
                        'index': i,
                        'timestamp': timestamp,
                        'event_type': 'tool_result',
                        'tool_id': content.get('tool_use_id'),
                        'status': 'error' if has_error else 'success',
                        'content_preview': result_content[:100]
                    })

        elif msg_type == 'assistant':
            for content in msg.get('message', {}).get('content', []):
                content_type = content.get('type')

                if content_type == 'text':
                    text = content.get('text', '')
                    if text:
                        timeline.append({
                            'index': i,
                            'timestamp': timestamp,
                            'event_type': 'assistant_message',
                            'content_preview': text[:100]
                        })

                elif content_type == 'tool_use':
                    timeline.append({
                        'index': i,
                        'timestamp': timestamp,
                        'event_type': 'tool_call',
                        'tool_name': content.get('name'),
                        'tool_id': content.get('id')
                    })

                elif content_type == 'tool_result':
                    is_error = content.get('is_error', False)
                    result_content = str(content.get('content', ''))
                    has_error = is_error or 'error' in result_content.lower()

                    timeline.append({
                        'index': i,
                        'timestamp': timestamp,
                        'event_type': 'tool_result',
                        'tool_id': content.get('tool_use_id'),
                        'status': 'error' if has_error else 'success',
                        'content_preview': result_content[:100]
                    })

                elif content_type == 'thinking':
                    thinking_text = content.get('thinking', '')
                    timeline.append({
                        'index': i,
                        'timestamp': timestamp,
                        'event_type': 'thinking',
                        'tokens_approx': len(thinking_text) // 4,
                        'content_preview': thinking_text[:100]
                    })

    base.update({
        'session': session_name,
        'event_count': len(timeline),
        'timeline': timeline
    })

    return base
