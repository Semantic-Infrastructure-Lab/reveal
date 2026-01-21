"""Error analysis functions for Claude sessions."""

from typing import Dict, List, Any

from ....utils.patterns import Patterns


def get_error_context(messages: List[Dict], error_msg_index: int,
                      tool_use_id: str) -> Dict[str, Any]:
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
    context = {
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

            # Found the tool_use that led to this error
            if content.get('type') == 'tool_use' and content.get('id') == tool_use_id:
                context['tool_name'] = content.get('name')
                tool_input = content.get('input', {})
                if isinstance(tool_input, dict):
                    # For Bash, show the command
                    if 'command' in tool_input:
                        context['tool_input_preview'] = tool_input['command'][:200]
                    # For Read/Edit, show the file path
                    elif 'file_path' in tool_input:
                        context['tool_input_preview'] = tool_input['file_path']
                    else:
                        # Generic: show first key-value
                        for k, v in tool_input.items():
                            context['tool_input_preview'] = f"{k}: {str(v)[:150]}"
                            break

            # Look for thinking in the same message
            if content.get('type') == 'thinking':
                thinking = content.get('thinking', '')
                # Get the last ~200 chars which is usually the decision
                if len(thinking) > 200:
                    context['thinking_preview'] = '...' + thinking[-200:]
                else:
                    context['thinking_preview'] = thinking

        # If we found the tool_use, we're done
        if context['tool_name']:
            break

    return context


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
        # Tool results are in 'user' type messages (results returned to assistant)
        if msg.get('type') == 'user':
            for content in msg.get('message', {}).get('content', []):
                # Skip non-dict content (plain text messages)
                if not isinstance(content, dict):
                    continue
                if content.get('type') == 'tool_result':
                    result_content = str(content.get('content', ''))

                    # Priority 1: Explicit is_error flag (definitive)
                    is_error = content.get('is_error', False)

                    # Priority 2: Exit code > 0 (definitive for Bash)
                    exit_match = exit_code_pattern.search(result_content)
                    has_exit_error = exit_match and int(exit_match.group(1)) > 0

                    # Priority 3: Strong error patterns at line start
                    has_strong_pattern = bool(strong_patterns.search(result_content))

                    error_type = None
                    if is_error:
                        error_type = 'is_error_flag'
                    elif has_exit_error:
                        error_type = 'exit_code'
                    elif has_strong_pattern:
                        error_type = 'pattern_match'

                    if error_type:
                        tool_use_id = content.get('tool_use_id')
                        context = get_error_context(messages, i, tool_use_id)

                        errors.append({
                            'message_index': i,
                            'tool_use_id': tool_use_id,
                            'error_type': error_type,
                            'content_preview': result_content[:300],
                            'timestamp': msg.get('timestamp'),
                            'context': context
                        })

    base.update({
        'session': session_name,
        'error_count': len(errors),
        'errors': errors
    })

    return base
