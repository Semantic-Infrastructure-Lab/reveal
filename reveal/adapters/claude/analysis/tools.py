"""Tool analysis functions for Claude sessions."""

from typing import Dict, List, Any, Optional
from collections import defaultdict

from ....utils.patterns import Patterns
from typing import Generator, Tuple


def _iter_assistant_content(messages: List[Dict]) -> Generator[Tuple[int, Dict, Dict], None, None]:
    """Yield (msg_index, msg, content_block) for each content block in assistant messages."""
    for i, msg in enumerate(messages):
        if msg.get('type') == 'assistant':
            for content in msg.get('message', {}).get('content', []):
                yield i, msg, content


def _iter_user_content(messages: List[Dict]) -> Generator[Tuple[int, Dict, Dict], None, None]:
    """Yield (msg_index, msg, content_block) for each content block in user messages."""
    for i, msg in enumerate(messages):
        if msg.get('type') != 'user':
            continue
        for content in msg.get('message', {}).get('content', []):
            if isinstance(content, dict):
                yield i, msg, content


def is_tool_error(content: Dict) -> bool:
    """Check if a tool result indicates an error.

    Uses multiple signals:
    - is_error flag (definitive)
    - Exit code > 0 (definitive for Bash)
    - Error patterns at line start (strong signal)

    Args:
        content: Tool result content dictionary

    Returns:
        True if the result indicates an error
    """
    # Check explicit is_error flag first (definitive)
    if content.get('is_error', False):
        return True

    result_content = str(content.get('content', ''))

    # Check for exit code > 0 (definitive for Bash)
    exit_match = Patterns.EXIT_CODE.search(result_content)
    if exit_match and int(exit_match.group(1)) > 0:
        return True

    # Check for strong error patterns at line start
    if Patterns.ERROR_LINE_START.search(result_content):
        return True

    return False


def _collect_tool_use_map(messages: List[Dict]) -> Dict[str, str]:
    """Build tool_use_id → tool_name mapping from assistant messages."""
    tool_use_map: Dict[str, str] = {}
    for _i, _msg, content in _iter_assistant_content(messages):
        if isinstance(content, dict) and content.get('type') == 'tool_use':
            tool_id = content.get('id')
            tool_name = content.get('name')
            if tool_id and tool_name:
                tool_use_map[tool_id] = tool_name
    return tool_use_map


def extract_all_tool_results(messages: List[Dict]) -> List[Dict]:
    """Extract all tool results with metadata for filtering.

    Args:
        messages: List of message dictionaries

    Returns:
        List of tool result dictionaries with:
        - message_index, tool_use_id, tool_name, content, is_error, timestamp
    """
    # First pass: collect tool_use_id -> tool_name mapping from assistant messages
    tool_use_map = _collect_tool_use_map(messages)

    results = []
    for i, msg, content in _iter_user_content(messages):
        if content.get('type') == 'tool_result':
            tool_id = str(content.get("tool_use_id", ""))
            results.append({
                'message_index': i,
                'tool_use_id': tool_id,
                'tool_name': tool_use_map.get(tool_id, 'unknown'),
                'content': str(content.get('content', ''))[:500],
                'is_error': is_tool_error(content),
                'timestamp': msg.get('timestamp')
            })
    return results


def get_tool_calls(messages: List[Dict], tool_name: str, session_name: str,
                   contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Extract all calls to specific tool.

    Args:
        messages: List of message dictionaries
        tool_name: Name of tool to filter (e.g., 'Bash', 'Read')
        session_name: Name of the session
        contract_base: Base contract fields

    Returns:
        Dictionary with tool call count and list of calls
    """
    base = contract_base.copy()
    base['type'] = 'claude_tool_calls'

    tool_calls = []
    for i, msg, content in _iter_assistant_content(messages):
        if content.get('type') == 'tool_use' and content.get('name') == tool_name:
            tool_calls.append({
                'message_index': i,
                'tool_use_id': content.get('id'),
                'input': content.get('input'),
                'timestamp': msg.get('timestamp')
            })

    base.update({
        'session': session_name,
        'tool_name': tool_name,
        'call_count': len(tool_calls),
        'calls': tool_calls
    })

    return base


def get_all_tools(messages: List[Dict], session_name: str,
                  contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Get all tool calls across all types with success rates.

    Args:
        messages: List of message dictionaries
        session_name: Name of the session
        contract_base: Base contract fields

    Returns:
        Dictionary with tool usage statistics including success rates
    """
    base = contract_base.copy()
    base['type'] = 'claude_tool_summary'

    tools = defaultdict(list)
    for i, msg, content in _iter_assistant_content(messages):
        if content.get('type') == 'tool_use':
            name = content.get('name')
            tools[name].append({
                'message_index': i,
                'tool_use_id': content.get('id'),
                'timestamp': msg.get('timestamp'),
                'detail': _extract_tool_detail(name, content.get('input', {}))
            })

    # Calculate success rates
    success_rates = calculate_tool_success_rate(messages)

    # Build tool statistics with counts and success rates
    tool_stats = {}
    for name, calls in tools.items():
        tool_stats[name] = {
            'count': len(calls),
            'success_rate': f"{success_rates.get(name, {}).get('success_rate', 0)}%",
            'success': success_rates.get(name, {}).get('success', 0),
            'failure': success_rates.get(name, {}).get('failure', 0),
        }

    base.update({
        'session': session_name,
        'total_calls': sum(len(calls) for calls in tools.values()),
        'tools': tool_stats,
        'details': dict(tools)
    })

    return base


def _collect_tool_use_ids(messages: List[Dict]) -> Dict[str, str]:
    """Extract mapping of tool_use_id to tool name from messages."""
    tool_use_map = {}
    for _i, _msg, content in _iter_assistant_content(messages):
        if content.get('type') == 'tool_use':
            tool_id = content.get('id')
            tool_name = content.get('name')
            if tool_id and tool_name:
                tool_use_map[tool_id] = tool_name
    return tool_use_map


def _track_tool_results(messages: List[Dict], tool_use_map: Dict[str, str],
                        tool_stats: Dict[str, Dict[str, int]]) -> None:
    """Track success/failure for each tool based on results.

    Args:
        messages: List of message dictionaries
        tool_use_map: Mapping of tool_use_id to tool name
        tool_stats: Dictionary to update with success/failure counts
    """
    for _i, _msg, content in _iter_user_content(messages):
        if content.get('type') != 'tool_result':
            continue
        tool_id = str(content.get("tool_use_id", ""))
        if tool_id not in tool_use_map:
            continue
        tool_name = tool_use_map[tool_id]
        tool_stats[tool_name]['total'] += 1
        if is_tool_error(content):
            tool_stats[tool_name]['failure'] += 1
        else:
            tool_stats[tool_name]['success'] += 1


def _build_success_rate_report(tool_stats: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, Any]]:
    """Build final success rate report from stats.

    Args:
        tool_stats: Dictionary of tool statistics

    Returns:
        Dictionary mapping tool names to success rate reports
    """
    result = {}
    for tool_name, stats in tool_stats.items():
        if stats['total'] > 0:
            success_rate = (stats['success'] / stats['total']) * 100
            result[tool_name] = {
                'success': stats['success'],
                'failure': stats['failure'],
                'total': stats['total'],
                'success_rate': round(success_rate, 1)
            }
    return result


def calculate_tool_success_rate(messages: List[Dict]) -> Dict[str, Dict[str, Any]]:
    """Calculate success rate per tool.

    Args:
        messages: List of message dictionaries

    Returns:
        Dictionary mapping tool names to success/failure stats
    """
    # Build mapping of tool_use_id to tool name
    tool_use_map = _collect_tool_use_ids(messages)

    # Track success/failure per tool
    tool_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {'success': 0, 'failure': 0, 'total': 0})
    _track_tool_results(messages, tool_use_map, tool_stats)

    # Calculate final success rates
    return _build_success_rate_report(tool_stats)


def _extract_file_operation(content: Dict[str, Any], msg_index: int,
                           timestamp: Optional[str]) -> Optional[Dict[str, Any]]:
    """Extract file operation from tool use content.

    Args:
        content: Content dictionary from message
        msg_index: Message index in conversation
        timestamp: Message timestamp

    Returns:
        Operation dict or None if not a file operation
    """
    if content.get('type') != 'tool_use':
        return None

    tool_name = content.get('name')
    if tool_name not in ('Read', 'Write', 'Edit'):
        return None

    file_path = content.get('input', {}).get('file_path')
    if not file_path:
        return None

    return {
        'message_index': msg_index,
        'operation': tool_name,
        'file_path': file_path,
        'timestamp': timestamp
    }


def get_files_touched(messages: List[Dict], session_name: str,
                      contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Get all files that were Read, Written, or Edited.

    Args:
        messages: List of message dictionaries
        session_name: Name of the session
        contract_base: Base contract fields

    Returns:
        Dictionary with file operation statistics
    """
    base = contract_base.copy()
    base['type'] = 'claude_files'

    files_by_op: Dict[str, Any] = {
        'Read': defaultdict(int),
        'Write': defaultdict(int),
        'Edit': defaultdict(int)
    }
    operations = []

    for i, msg in enumerate(messages):
        # Skip non-assistant messages
        if msg.get('type') != 'assistant':
            continue

        # Process each content block in assistant message
        for content in msg.get('message', {}).get('content', []):
            operation = _extract_file_operation(content, i, msg.get('timestamp'))
            if operation:
                tool_name = operation['operation']
                file_path = operation['file_path']
                files_by_op[tool_name][file_path] += 1
                operations.append(operation)

    # Calculate unique files
    all_files: set[str] = set()
    for op_files in files_by_op.values():
        all_files.update(op_files.keys())

    base.update({
        'session': session_name,
        'total_operations': len(operations),
        'unique_files': len(all_files),
        'by_operation': {
            op: dict(files) for op, files in files_by_op.items()
        },
        'operations': operations
    })

    return base


def _extract_tool_detail(tool_name: str, tool_input: Dict[str, Any]) -> Optional[str]:
    """Extract meaningful detail from tool input based on tool type.

    Args:
        tool_name: Name of the tool
        tool_input: Input parameters for the tool

    Returns:
        Detail string or None
    """
    if tool_name == 'Bash':
        return str(tool_input.get('description') or tool_input.get('command', ''))
    elif tool_name in ('Read', 'Write', 'Edit'):
        return str(tool_input.get('file_path', ''))
    elif tool_name == 'Grep':
        pattern = tool_input.get('pattern')
        path = tool_input.get('path', '.')
        return f"'{pattern}' in {path}"
    elif tool_name == 'Glob':
        return str(tool_input.get('pattern')) if tool_input.get('pattern') is not None else None
    elif tool_name in ('TaskCreate', 'TaskUpdate'):
        result = tool_input.get('subject') or tool_input.get('taskId')
        return str(result) if result is not None else None
    return None


def _collapse_workflow_runs(
    workflow: List[Dict[str, Any]], messages: List[Dict]
) -> List[Dict[str, Any]]:
    """Collapse consecutive identical tool+detail steps into single entries with run_count.

    When N consecutive steps share the same tool and detail, they are merged
    into one entry with ``run_count=N``.  A ``thinking_hint`` is added when
    a thinking block precedes the run in the same assistant message.
    """
    if not workflow:
        return workflow

    collapsed: List[Dict[str, Any]] = []
    i = 0
    while i < len(workflow):
        step = workflow[i]
        tool = step.get('tool')
        detail = step.get('detail')

        j = i + 1
        while (j < len(workflow)
               and workflow[j].get('tool') == tool
               and workflow[j].get('detail') == detail):
            j += 1
        run_count = j - i

        entry = dict(step)
        if run_count > 1:
            entry['run_count'] = run_count
            # Look for a thinking block in the same assistant message as the run start
            msg_idx = step.get('message_index')
            if msg_idx is not None and msg_idx < len(messages):
                for block in messages[msg_idx].get('message', {}).get('content', []):
                    if block.get('type') == 'thinking':
                        raw = block.get('thinking', '').strip()
                        if raw:
                            first_line = raw.split('\n')[0].strip()
                            if first_line:
                                entry['thinking_hint'] = first_line[:60]
                        break

        collapsed.append(entry)
        i = j

    # Renumber steps
    for idx, s in enumerate(collapsed, 1):
        s['step'] = idx

    return collapsed


def get_workflow(messages: List[Dict], session_name: str,
                 contract_base: Dict[str, Any]) -> Dict[str, Any]:
    """Get chronological sequence of tool operations.

    Args:
        messages: List of message dictionaries
        session_name: Name of the session
        contract_base: Base contract fields

    Returns:
        Dictionary with workflow sequence
    """
    base = contract_base.copy()
    base['type'] = 'claude_workflow'

    workflow: List[Dict[str, Any]] = []
    for i, msg, content in _iter_assistant_content(messages):
        if content.get('type') != 'tool_use':
            continue
        tool_name = content.get('name')
        workflow.append({
            'step': len(workflow) + 1,
            'message_index': i,
            'tool': tool_name,
            'detail': _extract_tool_detail(tool_name, content.get('input', {})),
            'timestamp': msg.get('timestamp')
        })

    total_steps = len(workflow)
    workflow = _collapse_workflow_runs(workflow, messages)

    base.update({
        'session': session_name,
        'total_steps': total_steps,
        'collapsed_steps': len(workflow),
        'workflow': workflow
    })

    return base
