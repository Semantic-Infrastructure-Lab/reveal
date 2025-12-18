"""Nginx configuration file analyzer."""

import re
from typing import Dict, List, Any, Optional
from ..base import FileAnalyzer, register


@register('.conf', name='Nginx', icon='')
class NginxAnalyzer(FileAnalyzer):
    """Nginx configuration file analyzer.

    Extracts server blocks, locations, upstreams, and key directives.
    """

    def _parse_server_block(self, line_num: int) -> Dict[str, Any]:
        """Parse server block starting at line_num."""
        server_info = {
            'line': line_num,
            'name': 'unknown',
            'port': 'unknown'
        }
        # Look ahead for server_name and listen
        for j in range(line_num, min(line_num + 20, len(self.lines) + 1)):
            next_line = self.lines[j-1].strip()
            if next_line.startswith('server_name '):
                match = re.match(r'server_name\s+(.*?);', next_line)
                if match:
                    server_info['name'] = match.group(1)
            elif next_line.startswith('listen '):
                match = re.match(r'listen\s+(\S+)', next_line)
                if match:
                    port = match.group(1).rstrip(';')
                    server_info['port'] = self._format_port(port)
            if next_line == '}' and j > line_num:
                break
        return server_info

    def _format_port(self, port: str) -> str:
        """Format port string for display."""
        if port.startswith('443'):
            return '443 (SSL)'
        if port.startswith('80'):
            return '80'
        return port

    def _parse_location_block(self, line_num: int, path: str, current_server: Optional[Dict]) -> Dict[str, Any]:
        """Parse location block starting at line_num."""
        loc_info = {
            'line': line_num,
            'name': path,
            'path': path,
            'server': current_server['name'] if current_server else 'unknown'
        }
        # Look ahead for proxy_pass or root
        for j in range(line_num, min(line_num + 15, len(self.lines) + 1)):
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
        return loc_info

    def get_structure(self, head: int = None, tail: int = None,
                      range: tuple = None, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        """Extract nginx config structure."""
        servers = []
        locations = []
        upstreams = []
        comments = []

        current_server = None
        in_server = False
        brace_depth = 0

        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()

            brace_depth += stripped.count('{') - stripped.count('}')

            # Top-level comment headers
            if stripped.startswith('#') and i <= 10 and len(stripped) > 3:
                comments.append({'line': i, 'text': stripped[1:].strip()})

            # Server block
            if 'server {' in stripped or stripped.startswith('server {'):
                in_server = True
                server_info = self._parse_server_block(i)
                servers.append(server_info)
                current_server = server_info

            # Location block (inside server)
            elif in_server and brace_depth > 0 and 'location ' in stripped:
                match = re.match(r'location\s+(.+?)\s*\{', stripped)
                if match:
                    loc_info = self._parse_location_block(i, match.group(1), current_server)
                    locations.append(loc_info)

            # Upstream block
            elif 'upstream ' in stripped and '{' in stripped:
                match = re.match(r'upstream\s+(\S+)\s*\{', stripped)
                if match:
                    upstreams.append({'line': i, 'name': match.group(1)})

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

    def _find_server_line(self, name: str) -> Optional[int]:
        """Find line number of server block with given server_name."""
        for i, line in enumerate(self.lines, 1):
            if 'server {' in line or line.strip().startswith('server {'):
                for j in range(i, min(i + 20, len(self.lines) + 1)):
                    if f'server_name {name}' in self.lines[j-1]:
                        return i
        return None

    def _find_block_line(self, pattern: str) -> Optional[int]:
        """Find line number matching given regex pattern."""
        for i, line in enumerate(self.lines, 1):
            if re.search(pattern, line):
                return i
        return None

    def _find_closing_brace(self, start_line: int) -> int:
        """Find matching closing brace for block starting at start_line."""
        brace_depth = 0
        for i in range(start_line - 1, len(self.lines)):
            line = self.lines[i]
            brace_depth += line.count('{') - line.count('}')
            if brace_depth == 0 and i >= start_line:
                return i + 1
        return start_line

    def extract_element(self, element_type: str, name: str) -> Optional[Dict[str, Any]]:
        """Extract a server or location block.

        Args:
            element_type: 'server', 'location', or 'upstream'
            name: Name to find (server_name, location path, or upstream name)

        Returns:
            Dict with block content
        """
        start_line = None

        if element_type == 'server':
            start_line = self._find_server_line(name)
        elif element_type == 'location':
            pattern = rf'location\s+{re.escape(name)}\s*\{{'
            start_line = self._find_block_line(pattern)
        elif element_type == 'upstream':
            pattern = rf'upstream\s+{re.escape(name)}\s*\{{'
            start_line = self._find_block_line(pattern)

        if not start_line:
            return super().extract_element(element_type, name)

        end_line = self._find_closing_brace(start_line)
        source = '\n'.join(self.lines[start_line-1:end_line])

        return {
            'name': name,
            'line_start': start_line,
            'line_end': end_line,
            'source': source,
        }
