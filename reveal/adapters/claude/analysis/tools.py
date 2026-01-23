"""Tool analysis functions for Claude sessions."""

from typing import Dict, List, Any
from collections import defaultdict

from ....utils.patterns import Patterns


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


def extract_all_tool_results(messages: List[Dict]) -> List[Dict]:
    """Extract all tool results with metadata for filtering.

    Args:
        messages: List of message dictionaries

    Returns:
        List of tool result dictionaries with:
        - message_index, tool_use_id, tool_name, content, is_error, timestamp
    """
    # First pass: collect tool_use_id -> tool_name mapping from assistant messages
    tool_use_map = {}
    for msg in messages:
        if msg.get('type') == 'assistant':
            for content in msg.get('message', {}).get('content', []):
                if isinstance(content, dict) and content.get('type') == 'tool_use':
                    tool_id = content.get('id')
                    tool_name = content.get('name')
                    if tool_id and tool_name:
                        tool_use_map[tool_id] = tool_name

    # Second pass: extract tool results from user messages
    results = []
    for i, msg in enumerate(messages):
        if msg.get('type') == 'user':
            for content in msg.get('message', {}).get('content', []):
                if not isinstance(content, dict):
                    continue
                if content.get('type') == 'tool_result':
                    tool_id = content.get('tool_use_id')
                    tool_name = tool_use_map.get(tool_id, 'unknown')
                    result_content = str(content.get('content', ''))

                    results.append({
                        'message_index': i,
                        'tool_use_id': tool_id,
                        'tool_name': tool_name,
                        'content': result_content[:500],  # Truncate for display
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

    for i, msg in enumerate(messages):
        if msg.get('type') == 'assistant':
            for content in msg.get('message', {}).get('content', []):
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

    # Collect tool call details
    tools = defaultdict(list)
    for i, msg in enumerate(messages):
        if msg.get('type') == 'assistant':
            for content in msg.get('message', {}).get('content', []):
                if content.get('type') == 'tool_use':
                    tool_name = content.get('name')
                    tools[tool_name].append({
                        'message_index': i,
                        'tool_use_id': content.get('id'),
                        'timestamp': msg.get('timestamp')
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
    """Extract mapping of tool_use_id to tool name from messages.

    Args:
        messages: List of message dictionaries

    Returns:
        Dictionary mapping tool_use_id to tool name
    """
    tool_use_map = {}
    for msg in messages:
        if msg.get('type') == 'assistant':
            for content in msg.get('message', {}).get('content', []):
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
    for msg in messages:
        # Tool results are in 'user' type messages (results returned to assistant)
        if msg.get('type') != 'user':
            continue

        for content in msg.get('message', {}).get('content', []):
            if not isinstance(content, dict):
                continue
            if content.get('type') != 'tool_result':
                continue

            tool_id = content.get('tool_use_id')
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
    tool_stats = defaultdict(lambda: {'success': 0, 'failure': 0, 'total': 0})
    _track_tool_results(messages, tool_use_map, tool_stats)

    # Calculate final success rates
    return _build_success_rate_report(tool_stats)


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

    files_by_op = {
        'Read': defaultdict(int),
        'Write': defaultdict(int),
        'Edit': defaultdict(int)
    }

    # Track all file operations in order
    operations = []

    for i, msg in enumerate(messages):
        if msg.get('type') == 'assistant':
            for content in msg.get('message', {}).get('content', []):
                if content.get('type') == 'tool_use':
                    tool_name = content.get('name')
                    if tool_name in ('Read', 'Write', 'Edit'):
                        inp = content.get('input', {})
                        file_path = inp.get('file_path')
                        if file_path:
                            files_by_op[tool_name][file_path] += 1
                            operations.append({
                                'message_index': i,
                                'operation': tool_name,
                                'file_path': file_path,
                                'timestamp': msg.get('timestamp')
                            })

    # Calculate unique files
    all_files = set()
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

    workflow = []

    for i, msg in enumerate(messages):
        if msg.get('type') == 'assistant':
            for content in msg.get('message', {}).get('content', []):
                if content.get('type') == 'tool_use':
                    tool_name = content.get('name')
                    inp = content.get('input', {})

                    # Extract key info based on tool type
                    detail = None
                    if tool_name == 'Bash':
                        detail = inp.get('description') or inp.get('command', '')[:60]
                    elif tool_name in ('Read', 'Write', 'Edit'):
                        detail = inp.get('file_path', '')
                    elif tool_name == 'Grep':
                        detail = f"'{inp.get('pattern')}' in {inp.get('path', '.')}"
                    elif tool_name == 'Glob':
                        detail = inp.get('pattern')
                    elif tool_name in ('TaskCreate', 'TaskUpdate'):
                        detail = inp.get('subject') or inp.get('taskId')

                    workflow.append({
                        'step': len(workflow) + 1,
                        'message_index': i,
                        'tool': tool_name,
                        'detail': detail,
                        'timestamp': msg.get('timestamp')
                    })

    base.update({
        'session': session_name,
        'total_steps': len(workflow),
        'workflow': workflow
    })

    return base
