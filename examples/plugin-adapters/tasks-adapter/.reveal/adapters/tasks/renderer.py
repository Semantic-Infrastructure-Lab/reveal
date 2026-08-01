"""Renderer for tasks:// adapter results."""

import sys

from reveal.utils import print_json_result


class TasksRenderer:
    """Renders TasksAdapter results for text/json/grep output."""

    @staticmethod
    def render_structure(result: dict, format: str = 'text') -> None:
        if format == 'json':
            print_json_result(result)
            return

        tasks = result.get('tasks', [])
        if format == 'grep':
            for t in tasks:
                print(f"{t['id']}:{t['status']}:{t['priority']}:{t['title']}")
            return

        print(f"Tasks ({len(tasks)}):")
        for t in tasks:
            print(f"  [{t['status']:8s}] [{t['priority']:6s}] {t['id']}: {t['title']}")

    @staticmethod
    def render_element(result: dict, format: str = 'text') -> None:
        if format == 'json':
            print_json_result(result)
            return

        if result is None:
            print("Task not found", file=sys.stderr)
            return

        print(f"{result['id']}: {result['title']}")
        print(f"  status:   {result['status']}")
        print(f"  priority: {result['priority']}")
        if result.get('description'):
            print()
            print(result['description'])

    @staticmethod
    def render_error(error: Exception) -> None:
        print(f"Error accessing tasks: {error}", file=sys.stderr)
