"""Error analysis functions for Claude sessions."""

from typing import Dict, List, Any, Optional

from ....utils.patterns import Patterns


def _get_tool_input_preview(tool_input: dict) -> Optional[str]:
    """Extract a short preview string from a tool_use input dict."""
    if 'command' in tool_input:
        return str(tool_input["command"])[:200]
    if 'file_path' in tool_input:
        return str(tool_input["file_path"])
    for k, v in tool_input.items():
        return f"{k}: {str(v)[:150]}"
    return None


def get_error_context(messages: List[Dict], error_msg_index: int,
                      tool_use_id: Optional[str]) -> Dict[str, Any]:
    """Get context around an error for debugging.

    Looks backwards from the error to find:
    - The tool_use call that triggered the error
    - Any thinking before the tool call
    - The tool name and input

    Args:
        messages: List of message dictionaries
        error_msg_index: Index of the message containing the error
        tool_use_id: The tool_use_id that resulted in the error

    Returns:
        Context dictionary with tool_call, thinking, and prior_action
    """
    context: Dict[str, Any] = {
        'tool_name': None,
        'tool_input_preview': None,
        'thinking_preview': None,
        'prior_action': None
    }

    # Look backwards from the error message to find the tool_use
    for i in range(error_msg_index - 1, max(0, error_msg_index - 10), -1):
        msg = messages[i]
        if msg.get('type') != 'assistant':
            continue

        contents = msg.get('message', {}).get('content', [])
        for content in contents:
            if not isinstance(content, dict):
                continue

            if content.get('type') == 'tool_use' and content.get('id') == tool_use_id:
                context['tool_name'] = content.get('name')
                tool_input = content.get('input', {})
                context['tool_input_preview'] = _get_tool_input_preview(tool_input) if isinstance(tool_input, dict) else None

            if content.get('type') == 'thinking':
                thinking = content.get('thinking', '')
                context['thinking_preview'] = ('...' + thinking[-200:]) if len(thinking) > 200 else thinking

        # If we found the tool_use, we're done
        if context['tool_name']:
            break

    return context


def _classify_tool_result(content, msg, i, messages, strong_patterns, exit_code_pattern):
    """Check a content block for errors and return an error dict or None."""
    if not isinstance(content, dict) or content.get('type') != 'tool_result':
        return None
    result_content = str(content.get('content', ''))
    is_error = content.get('is_error', False)
    exit_match = exit_code_pattern.search(result_content)
    has_exit_error = exit_match and int(exit_match.group(1)) > 0
    has_strong_pattern = bool(strong_patterns.search(result_content))
    if is_error:
        error_type = 'is_error_flag'
    elif has_exit_error:
        error_type = 'exit_code'
    elif has_strong_pattern:
        error_type = 'pattern_match'
    else:
        return None
    tool_use_id = content.get('tool_use_id')
    return {
        'message_index': i,
        'tool_use_id': tool_use_id,
        'error_type': error_type,
        'content_preview': result_content[:300],
        'timestamp': msg.get('timestamp'),
        'context': get_error_context(messages, i, tool_use_id),
    }


def get_errors(messages: List[Dict], session_name: str,
               contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Extract all errors with context.

    Detects errors through multiple signals (in priority order):
    1. is_error: true in tool_result (definitive)
    2. Exit codes > 0 in Bash output (definitive)
    3. Traceback/Exception at start of line (strong signal)
    4. Common error patterns at start of content (moderate signal)

    Avoids false positives by NOT matching error keywords mid-content
    (e.g., documentation mentioning "error handling").

    Args:
        messages: List of message dictionaries
        session_name: Name of the session
        contract_base: Base contract fields

    Returns:
        Dictionary with error count and list of errors
    """
    base = contract_base.copy()
    base['type'] = 'claude_errors'

    errors = []

    # Use centralized patterns from utils.patterns
    strong_patterns = Patterns.ERROR_LINE_START
    exit_code_pattern = Patterns.EXIT_CODE

    for i, msg in enumerate(messages):
        if msg.get('type') != 'user':
            continue
        for content in msg.get('message', {}).get('content', []):
            error = _classify_tool_result(content, msg, i, messages, strong_patterns, exit_code_pattern)
            if error:
                errors.append(error)

    base.update({
        'session': session_name,
        'error_count': len(errors),
        'errors': errors
    })

    return base
