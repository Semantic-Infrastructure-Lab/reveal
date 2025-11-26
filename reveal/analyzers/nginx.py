"""Nginx configuration file analyzer."""

import re
from typing import Dict, List, Any, Optional
from ..base import FileAnalyzer, register


@register('.conf', name='Nginx', icon='')
class NginxAnalyzer(FileAnalyzer):
    """Nginx configuration file analyzer.

    Extracts server blocks, locations, upstreams, and key directives.
    """

    def get_structure(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extract nginx config structure."""
        servers = []
        locations = []
        upstreams = []
        comments = []

        # Track current context for locations
        current_server = None
        in_server = False
        brace_depth = 0

        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()

            # Track brace depth
            brace_depth += stripped.count('{')
            brace_depth -= stripped.count('}')

            # Top-level comment headers (typically file documentation)
            if stripped.startswith('#') and i <= 10 and len(stripped) > 3:
                comments.append({
                    'line': i,
                    'text': stripped[1:].strip()
                })

            # Server block
            if 'server {' in stripped or stripped.startswith('server {'):
                in_server = True
                server_info = {
                    'line': i,
                    'name': 'unknown',
                    'port': 'unknown'
                }
                # Look ahead for server_name and listen
                for j in range(i, min(i + 20, len(self.lines) + 1)):
                    next_line = self.lines[j-1].strip()
                    if next_line.startswith('server_name '):
                        match = re.match(r'server_name\s+(.*?);', next_line)
                        if match:
                            server_info['name'] = match.group(1)
                    elif next_line.startswith('listen '):
                        match = re.match(r'listen\s+(\S+)', next_line)
                        if match:
                            port = match.group(1).rstrip(';')
                            # Handle various listen formats
                            if port.startswith('443'):
                                server_info['port'] = '443 (SSL)'
                            elif port.startswith('80'):
                                server_info['port'] = '80'
                            else:
                                server_info['port'] = port
                    # Stop at closing brace of this server block
                    if next_line == '}' and j > i:
                        break

                servers.append(server_info)
                current_server = server_info

            # Location block (inside server)
            elif in_server and brace_depth > 0 and ('location ' in stripped):
                match = re.match(r'location\s+(.+?)\s*\{', stripped)
                if match:
                    path = match.group(1)
                    loc_info = {
                        'line': i,
                        'path': path,
                        'server': current_server['name'] if current_server else 'unknown'
                    }

                    # Look ahead for proxy_pass or root
                    for j in range(i, min(i + 15, len(self.lines) + 1)):
                        next_line = self.lines[j-1].strip()
                        if next_line.startswith('proxy_pass '):
                            match_proxy = re.match(r'proxy_pass\s+(.*?);', next_line)
                            if match_proxy:
                                loc_info['target'] = match_proxy.group(1)
                                break
                        elif next_line.startswith('root '):
                            match_root = re.match(r'root\s+(.*?);', next_line)
                            if match_root:
                                loc_info['target'] = f"static: {match_root.group(1)}"
                                break

                    locations.append(loc_info)

            # Upstream block
            elif 'upstream ' in stripped and '{' in stripped:
                match = re.match(r'upstream\s+(\S+)\s*\{', stripped)
                if match:
                    upstreams.append({
                        'line': i,
                        'name': match.group(1)
                    })

            # Reset server context when we exit server block
            if in_server and brace_depth == 0:
                in_server = False
                current_server = None

        return {
            'comments': comments,
            'servers': servers,
            'locations': locations,
            'upstreams': upstreams
        }

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a server or location block.

        Args:
            element_type: 'server', 'location', or 'upstream'
            name: Name to find (server_name, location path, or upstream name)

        Returns:
            Dict with block content
        """
        start_line = None
        search_pattern = None

        # Build search pattern based on element type
        if element_type == 'server':
            # Search for server block with this server_name
            for i, line in enumerate(self.lines, 1):
                if 'server {' in line or line.strip().startswith('server {'):
                    # Look ahead for server_name
                    for j in range(i, min(i + 20, len(self.lines) + 1)):
                        if f'server_name {name}' in self.lines[j-1]:
                            start_line = i
                            break
                    if start_line:
                        break

        elif element_type == 'location':
            # Search for location block with this path
            search_pattern = rf'location\s+{re.escape(name)}\s*\{{'
            for i, line in enumerate(self.lines, 1):
                if re.search(search_pattern, line):
                    start_line = i
                    break

        elif element_type == 'upstream':
            # Search for upstream block with this name
            search_pattern = rf'upstream\s+{re.escape(name)}\s*\{{'
            for i, line in enumerate(self.lines, 1):
                if re.search(search_pattern, line):
                    start_line = i
                    break

        if not start_line:
            return super().extract_element(element_type, name)

        # Find matching closing brace
        brace_depth = 0
        end_line = start_line
        for i in range(start_line - 1, len(self.lines)):
            line = self.lines[i]
            brace_depth += line.count('{')
            brace_depth -= line.count('}')
            if brace_depth == 0 and i >= start_line:
                end_line = i + 1
                break

        source = '\n'.join(self.lines[start_line-1:end_line])

        return {
            'name': name,
            'line_start': start_line,
            'line_end': end_line,
            'source': source,
        }
