"""Parser for the plain markdown+YAML task-file format used by this example.

Format (generic — no dependency on any particular task tracker):

    ## TASK-1: Fix the login timeout bug
    ```yaml
    status: open
    priority: high
    ```
    Free-text description goes here, until the next `## ` heading.

Each task is a level-2 markdown heading of the form `## <id>: <title>`,
immediately followed by a fenced ```yaml``` block holding `status` and
`priority`. Everything after the fence up to the next `## ` heading (or EOF)
is the task's description.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

import yaml

_TASK_HEADING_RE = re.compile(r'^##\s+(?P<id>\S+):\s*(?P<title>.+)$')
_YAML_FENCE_RE = re.compile(r'^```yaml\s*$')
_FENCE_END_RE = re.compile(r'^```\s*$')


def parse_tasks_file(path: Path) -> List[Dict[str, Any]]:
    """Parse a tasks markdown file into a list of task dicts.

    Each task dict has: id, title, status, priority, description.
    Malformed entries (missing yaml block, unparsable yaml) are skipped
    rather than raising, so one bad task doesn't hide the rest.
    """
    lines = path.read_text().splitlines()
    tasks: List[Dict[str, Any]] = []
    i = 0
    n = len(lines)

    while i < n:
        heading = _TASK_HEADING_RE.match(lines[i])
        if not heading:
            i += 1
            continue

        task_id = heading.group('id')
        title = heading.group('title').strip()
        i += 1

        # Skip blank lines before the yaml fence.
        while i < n and not lines[i].strip():
            i += 1

        fields: Dict[str, Any] = {}
        if i < n and _YAML_FENCE_RE.match(lines[i]):
            i += 1
            yaml_lines: List[str] = []
            while i < n and not _FENCE_END_RE.match(lines[i]):
                yaml_lines.append(lines[i])
                i += 1
            i += 1  # consume closing fence
            try:
                parsed = yaml.safe_load('\n'.join(yaml_lines)) or {}
                if isinstance(parsed, dict):
                    fields = parsed
            except yaml.YAMLError:
                pass

        # Description: everything up to the next '## ' heading or EOF.
        desc_lines: List[str] = []
        while i < n and not _TASK_HEADING_RE.match(lines[i]):
            desc_lines.append(lines[i])
            i += 1
        description = '\n'.join(desc_lines).strip()

        tasks.append({
            'id': task_id,
            'title': title,
            'status': fields.get('status', 'unknown'),
            'priority': fields.get('priority', 'unknown'),
            'description': description,
        })

    return tasks
