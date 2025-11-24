"""Dockerfile analyzer."""

import re
from typing import Dict, List, Any, Optional
from ..base import FileAnalyzer, register


@register('Dockerfile', name='Dockerfile', icon='🐳')
class DockerfileAnalyzer(FileAnalyzer):
    """Dockerfile analyzer.

    Extracts Docker directives (FROM, RUN, COPY, ENV, EXPOSE, etc.).
    """

    def get_structure(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract Dockerfile directives."""
        from_images = []
        runs = []
        copies = []
        envs = []
        exposes = []
        workdirs = []
        entrypoints = []
        cmds = []
        labels = []
        args = []

        # Track multi-line continuations
        continued_line = ""
        continued_start = 0

        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()

            # Handle line continuations (\)
            if continued_line:
                continued_line += " " + stripped.rstrip('\\')
                if not stripped.endswith('\\'):
                    # Process the complete continued line
                    self._process_directive(
                        continued_line, continued_start,
                        from_images, runs, copies, envs, exposes,
                        workdirs, entrypoints, cmds, labels, args
                    )
                    continued_line = ""
                continue

            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                continue

            # Check for line continuation
            if stripped.endswith('\\'):
                continued_line = stripped.rstrip('\\')
                continued_start = i
                continue

            # Process single-line directive
            self._process_directive(
                stripped, i,
                from_images, runs, copies, envs, exposes,
                workdirs, entrypoints, cmds, labels, args
            )

        # Build result
        result = {}
        if from_images:
            result['from'] = from_images
        if runs:
            result['run'] = runs
        if copies:
            result['copy'] = copies
        if envs:
            result['env'] = envs
        if exposes:
            result['expose'] = exposes
        if workdirs:
            result['workdir'] = workdirs
        if entrypoints:
            result['entrypoint'] = entrypoints
        if cmds:
            result['cmd'] = cmds
        if labels:
            result['label'] = labels
        if args:
            result['arg'] = args

        return result

    def _process_directive(self, line: str, line_num: int,
                          from_images, runs, copies, envs, exposes,
                          workdirs, entrypoints, cmds, labels, args):
        """Process a single Dockerfile directive."""
        # Match directive at start of line
        directive_match = re.match(r'^([A-Z]+)\s+(.+)$', line)
        if not directive_match:
            return

        directive = directive_match.group(1)
        args_str = directive_match.group(2).strip()

        if directive == 'FROM':
            # Extract base image
            from_images.append({
                'line': line_num,
                'name': args_str,
            })

        elif directive == 'RUN':
            # Truncate long commands
            display = args_str[:80] + '...' if len(args_str) > 80 else args_str
            runs.append({
                'line': line_num,
                'content': display,
            })

        elif directive in ['COPY', 'ADD']:
            # Extract source -> dest
            copies.append({
                'line': line_num,
                'content': args_str,
            })

        elif directive == 'ENV':
            # Extract environment variable
            envs.append({
                'line': line_num,
                'content': args_str,
            })

        elif directive == 'EXPOSE':
            # Extract port
            exposes.append({
                'line': line_num,
                'content': args_str,
            })

        elif directive == 'WORKDIR':
            workdirs.append({
                'line': line_num,
                'content': args_str,
            })

        elif directive == 'ENTRYPOINT':
            entrypoints.append({
                'line': line_num,
                'content': args_str,
            })

        elif directive == 'CMD':
            cmds.append({
                'line': line_num,
                'content': args_str,
            })

        elif directive == 'LABEL':
            labels.append({
                'line': line_num,
                'content': args_str,
            })

        elif directive == 'ARG':
            args.append({
                'line': line_num,
                'content': args_str,
            })

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a specific directive or stage.

        Args:
            element_type: 'from', 'run', etc.
            name: Search term

        Returns:
            Dict with directive content
        """
        # Fall back to grep-based search
        return super().extract_element(element_type, name)
