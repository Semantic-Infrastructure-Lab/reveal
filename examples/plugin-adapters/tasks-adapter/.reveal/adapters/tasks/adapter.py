"""tasks:// adapter — reference example of a third-party reveal plugin.

Demonstrates the plugin discovery mechanism (BACK-256): dropped into
<project>/.reveal/adapters/tasks/, this package is auto-discovered on `cd`
into the project, no installation or reveal-core changes required. See this
example's README.md for a walkthrough and
reveal/docs/development/ADAPTER_AUTHORING_GUIDE.md's "Writing Adapters for
External Projects" section for the mechanism itself.

Reads a plain markdown+YAML task file (see parser.py for the format) and
exposes it for querying:

    reveal 'tasks://TASKS.md'                # all tasks
    reveal 'tasks://TASKS.md?status=open'     # filter by status
    reveal 'tasks://TASKS.md?priority=high'   # filter by priority
    reveal tasks://TASKS.md TASK-1            # a single task by id
"""

from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs

# Absolute import — required for a plugin living outside reveal core (see
# ADAPTER_AUTHORING_GUIDE.md). A relative `from ..base import ...` only
# works for adapters shipped inside the reveal package itself.
from reveal.adapters.base import ResourceAdapter, register_adapter, register_renderer
from reveal.utils.results import ResultBuilder

from .parser import parse_tasks_file
from .renderer import TasksRenderer


@register_adapter('tasks')
@register_renderer(TasksRenderer)
class TasksAdapter(ResourceAdapter):
    """Adapter for exploring a markdown+YAML task file via tasks:// URIs."""

    BUDGET_LIST_FIELD = 'tasks'

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        return {
            'adapter': 'tasks',
            'description': 'Query a plain markdown+YAML task file (id/status/priority)',
            'uri_syntax': 'tasks://<path-to-file>[?status=X][&priority=Y]',
            'query_params': {
                'status': {
                    'type': 'string',
                    'description': 'Filter by status (e.g. open, done)',
                },
                'priority': {
                    'type': 'string',
                    'description': 'Filter by priority (e.g. high, low)',
                },
            },
            'elements': {
                '<task-id>': {'description': 'A single task by its id, e.g. TASK-1'},
            },
            'cli_flags': [],
            'supports_batch': False,
            'supports_advanced': False,
            'output_types': [
                {
                    'type': 'tasks_structure',
                    'description': 'List of tasks matching the query',
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'type': {'type': 'string', 'const': 'tasks_structure'},
                            'tasks': {'type': 'array'},
                        }
                    }
                }
            ],
            'example_queries': [
                {
                    'uri': 'tasks://TASKS.md',
                    'description': 'List all tasks',
                    'output_type': 'tasks_structure',
                },
                {
                    'uri': 'tasks://TASKS.md?status=open',
                    'description': 'List open tasks',
                    'output_type': 'tasks_structure',
                },
            ],
        }

    @staticmethod
    def get_help() -> Dict[str, Any]:
        return {
            'name': 'tasks',
            'description': 'Explore a plain markdown+YAML task file',
            'syntax': 'tasks://<path>[?status=X][&priority=Y]',
            'examples': [
                {'uri': 'tasks://TASKS.md', 'description': 'List all tasks'},
                {'uri': 'tasks://TASKS.md?status=open', 'description': 'Only open tasks'},
                {
                    'uri': 'tasks://TASKS.md?priority=high',
                    'description': 'Only high-priority tasks',
                },
            ],
            'features': [
                'Generic markdown+YAML task format, no tracker dependency',
                'Filter by status and/or priority via query params',
                'Fetch a single task by id as an element',
            ],
            'try_now': [
                "reveal 'tasks://TASKS.md'",
                "reveal 'tasks://TASKS.md?status=open'",
                "reveal tasks://TASKS.md TASK-1",
            ],
            'workflows': [
                {
                    'name': 'Triage open work',
                    'scenario': 'See what is still open, highest priority first',
                    'steps': [
                        "reveal 'tasks://TASKS.md?status=open'",
                        "reveal tasks://TASKS.md TASK-1   # drill into one task",
                    ],
                },
            ],
            'output_formats': ['text', 'json', 'grep'],
            'see_also': [],
        }

    def __init__(self, path: str, query_string: Optional[str] = None) -> None:
        """path is the task file; query_string (e.g. 'status=open&priority=high') filters it."""
        if not path:
            raise ValueError("tasks:// requires a file path, e.g. tasks://TASKS.md")
        self.path = Path(path)
        query_params = {k: v[0] for k, v in parse_qs(query_string or '').items()}
        self.status_filter = query_params.get('status')
        self.priority_filter = query_params.get('priority')

    def _load(self):
        tasks = parse_tasks_file(self.path)
        if self.status_filter:
            tasks = [t for t in tasks if t['status'] == self.status_filter]
        if self.priority_filter:
            tasks = [t for t in tasks if t['priority'] == self.priority_filter]
        return tasks

    def get_structure(self, **kwargs: Any) -> Dict[str, Any]:
        tasks = self._load()
        return ResultBuilder.create(
            result_type='tasks_structure',
            source=str(self.path),
            contract_version='1.1',
            data={
                'tasks': tasks,
                'metadata': {'total_count': len(tasks)},
            }
        )

    def get_element(self, element_name: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        for task in parse_tasks_file(self.path):
            if task['id'] == element_name:
                return task
        return None

    def get_metadata(self) -> Dict[str, Any]:
        return {'type': 'tasks', 'adapter_version': '1.0', 'source': str(self.path)}
