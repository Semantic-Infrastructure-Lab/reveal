"""Nginx configuration file analyzer."""

import re
from typing import Dict, List, Any, Optional
from ..base import FileAnalyzer
from ..registry import register


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
            'port': 'unknown',
            'domains': [],  # All domains from server_name directive
            'is_ssl': False,
        }
        # Look ahead for server_name and listen
        for j in range(line_num, min(line_num + 30, len(self.lines) + 1)):
            next_line = self.lines[j-1].strip()
            if next_line.startswith('server_name '):
                match = re.match(r'server_name\s+(.*?);', next_line)
                if match:
                    # Parse all domains (space-separated)
                    domains_str = match.group(1)
                    domains = [d.strip() for d in domains_str.split() if d.strip()]
                    server_info['domains'] = domains
                    server_info['name'] = domains[0] if domains else 'unknown'
            elif next_line.startswith('listen '):
                match = re.match(r'listen\s+(\S+)', next_line)
                if match:
                    port = match.group(1).rstrip(';')
                    server_info['port'] = self._format_port(port)
                    # Check if SSL
                    if '443' in port or 'ssl' in next_line.lower():
                        server_info['is_ssl'] = True
            elif 'ssl_certificate' in next_line:
                server_info['is_ssl'] = True
            if next_line == '}' and j > line_num:
                break
        # Add signature for display (shows port after name)
        server_info['signature'] = f" [{server_info['port']}]"
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

    def _parse_block_directives(self, block_name: str) -> Dict[str, str]:
        """Parse key-value directives from a top-level named block (e.g. http, events).

        Collects only direct-child directives (depth 1 inside the block),
        skipping nested blocks like server{}, map{}, upstream{}.
        Handles multi-line directives (e.g. log_format spanning multiple lines).

        Returns:
            Dict mapping directive name -> value string (without trailing semicolon).
        """
        directives: Dict[str, str] = {}
        depth = 0
        in_block = False
        block_pattern = re.compile(r'^' + re.escape(block_name) + r'\s*\{')
        pending_key: Optional[str] = None
        pending_parts: List[str] = []

        for line in self.lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            if not in_block and depth == 0 and block_pattern.match(stripped):
                in_block = True
                depth += stripped.count('{') - stripped.count('}')
                continue

            if in_block:
                # Accumulating a multi-line directive value
                if pending_key is not None:
                    pending_parts.append(stripped.rstrip(';').rstrip())
                    if ';' in stripped:
                        directives[pending_key] = ' '.join(pending_parts)
                        pending_key = None
                        pending_parts = []
                    continue  # don't update depth for continuation lines

                opens = stripped.count('{')
                closes = stripped.count('}')

                if depth == 1 and opens == 0 and not stripped.startswith('}'):
                    match = re.match(r'^([\w_-]+)\s+(.+)', stripped)
                    if match:
                        key, rest = match.group(1), match.group(2)
                        if ';' in stripped:
                            # Single-line directive
                            directives[key] = rest.rstrip(';').rstrip()
                        else:
                            # Start of multi-line directive
                            pending_key = key
                            pending_parts = [rest.rstrip()]

                depth += opens - closes
                if depth <= 0:
                    break  # exited the block

        return directives

    def _parse_main_directives(self) -> Dict[str, str]:
        """Parse key-value directives at the main (outermost) context — depth 0.

        Captures directives like user, worker_processes, error_log, pid in
        nginx.conf, and ssl_protocols, client_max_body_size, etc. in vhost
        include files. Skips block openers (events{}, http{}, map{}, etc.)

        Returns:
            Dict mapping directive name -> value string (without trailing semicolon).
        """
        directives: Dict[str, str] = {}
        depth = 0
        pending_key: Optional[str] = None
        pending_parts: List[str] = []

        for line in self.lines:
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue

            if pending_key is not None:
                # Continuation of multi-line directive
                pending_parts.append(stripped.rstrip(';').rstrip())
                depth += stripped.count('{') - stripped.count('}')
                if ';' in stripped:
                    directives[pending_key] = ' '.join(pending_parts)
                    pending_key = None
                    pending_parts = []
                continue

            opens = stripped.count('{')
            closes = stripped.count('}')

            if depth == 0 and not stripped.startswith('}'):
                if opens == 0 and ';' in stripped:
                    # Single-line top-level directive
                    match = re.match(r'^([\w_-]+)\s+(.+?)\s*;', stripped)
                    if match:
                        directives[match.group(1)] = match.group(2)
                elif opens == 0:
                    # Possible start of multi-line top-level directive
                    match = re.match(r'^([\w_-]+)\s+(.+)', stripped)
                    if match:
                        pending_key = match.group(1)
                        pending_parts = [match.group(2).rstrip()]

            depth += opens - closes

        return directives

    def _parse_upstream_servers(self, line_num: int) -> Dict[str, Any]:
        """Parse upstream block body, extracting server entries and key settings.

        Args:
            line_num: 1-based line number where the upstream block starts.

        Returns:
            Dict with 'servers' (list of dicts with 'address' + optional 'params')
            and 'settings' (dict of other directives like keepalive).
        """
        servers: List[Dict[str, str]] = []
        settings: Dict[str, str] = {}
        depth = 0

        for i in range(line_num - 1, len(self.lines)):
            line = self.lines[i]
            stripped = line.strip()
            depth += stripped.count('{') - stripped.count('}')

            if depth <= 0 and i >= line_num:
                break

            if not stripped or stripped.startswith('#') or '{' in stripped:
                continue

            if stripped.startswith('server '):
                match = re.match(r'server\s+(\S+)(.*?)\s*;', stripped)
                if match:
                    addr = match.group(1)
                    params = match.group(2).strip()
                    entry: Dict[str, str] = {'address': addr}
                    if params:
                        entry['params'] = params
                    servers.append(entry)
            elif ';' in stripped:
                m = re.match(r'^([\w_-]+)\s+(.+?)\s*;', stripped)
                if m:
                    settings[m.group(1)] = m.group(2)

        return {'servers': servers, 'settings': settings}

    def _try_parse_map_block(self, stripped: str) -> Optional[Dict[str, str]]:
        """Try to parse map block source/target variables from line."""
        match = re.match(r'map\s+(\S+)\s+(\S+)\s*\{', stripped)
        if match:
            return {'source': match.group(1), 'target': match.group(2)}
        return None

    def _is_top_level_comment(self, stripped: str, line_num: int) -> bool:
        """Check if line is a top-level comment header."""
        return stripped.startswith('#') and line_num <= 10 and len(stripped) > 3

    def _is_server_block_start(self, stripped: str) -> bool:
        """Check if line starts a server block."""
        return 'server {' in stripped or stripped.startswith('server {')

    def _try_parse_location_block(self, stripped: str) -> Optional[str]:
        """Try to parse location path from line."""
        match = re.match(r'location\s+(.+?)\s*\{', stripped)
        return match.group(1) if match else None

    def _try_parse_upstream_block(self, stripped: str) -> Optional[str]:
        """Try to parse upstream name from line."""
        match = re.match(r'upstream\s+(\S+)\s*\{', stripped)
        return match.group(1) if match else None

    def _process_comment(self, comments: List, stripped: str, line_num: int) -> None:
        """Process and add comment to list if it's a top-level header."""
        if self._is_top_level_comment(stripped, line_num):
            comments.append({'line': line_num, 'text': stripped[1:].strip()})

    def _process_server_block(self, servers: List, line_num: int) -> tuple:
        """Process server block and return (server_info, should_enter_server)."""
        server_info = self._parse_server_block(line_num)
        servers.append(server_info)
        return server_info, True

    def _process_location_block(self, locations: List, stripped: str, line_num: int,
                                 in_server: bool, brace_depth: int, current_server: Optional[Dict]) -> None:
        """Process location block if inside server context."""
        if in_server and brace_depth > 0 and 'location ' in stripped:
            location_path = self._try_parse_location_block(stripped)
            if location_path:
                loc_info = self._parse_location_block(line_num, location_path, current_server)
                locations.append(loc_info)

    def _process_upstream_block(self, upstreams: List, stripped: str, line_num: int) -> None:
        """Process upstream block if detected, extracting server entries and settings."""
        if 'upstream ' in stripped and '{' in stripped:
            upstream_name = self._try_parse_upstream_block(stripped)
            if upstream_name:
                detail = self._parse_upstream_servers(line_num)
                servers = detail['servers']
                settings = detail['settings']
                if servers:
                    first = servers[0]['address']
                    sig = f" [{first}]" if len(servers) == 1 else f" [{first}, +{len(servers)-1} more]"
                else:
                    sig = ''
                upstreams.append({
                    'line': line_num,
                    'name': upstream_name,
                    'servers': servers,
                    'settings': settings,
                    'signature': sig,
                })

    def get_structure(self, head: Optional[int] = None, tail: Optional[int] = None,
                      range: Optional[tuple] = None, **kwargs) -> Dict[str, Any]:
        """Extract nginx config structure."""
        servers: List[Dict[str, Any]] = []
        locations: List[Dict[str, Any]] = []
        upstreams: List[Dict[str, Any]] = []
        maps: List[Dict[str, Any]] = []
        comments: List[Dict[str, Any]] = []

        current_server = None
        in_server = False
        brace_depth = 0

        for i, line in enumerate(self.lines, 1):
            stripped = line.strip()
            brace_depth += stripped.count('{') - stripped.count('}')

            self._process_comment(comments, stripped, i)

            if self._is_server_block_start(stripped):
                current_server, in_server = self._process_server_block(servers, i)
            else:
                self._process_location_block(locations, stripped, i, in_server, brace_depth, current_server)
                self._process_upstream_block(upstreams, stripped, i)
                if 'map ' in stripped and '{' in stripped:
                    map_info = self._try_parse_map_block(stripped)
                    if map_info:
                        maps.append({
                            'line': i,
                            'name': f"{map_info['source']} → {map_info['target']}",
                            'source_var': map_info['source'],
                            'target_var': map_info['target'],
                        })

            # Reset server context when we exit server block
            if in_server and brace_depth == 0:
                in_server = False
                current_server = None

        main_directives = self._parse_main_directives()
        http_directives = self._parse_block_directives('http')
        events_directives = self._parse_block_directives('events')

        result: Dict[str, Any] = {
            'contract_version': '1.0',
            'type': 'nginx_structure',
            'source': str(self.path),
            'source_type': 'file',
            'comments': comments,
        }
        if main_directives:
            result['main_directives'] = main_directives
        result['servers'] = servers
        result['locations'] = locations
        result['upstreams'] = upstreams
        if maps:
            result['maps'] = maps
        if http_directives:
            result['directives'] = http_directives
        if events_directives:
            result['events_directives'] = events_directives
        return result

    def extract_ssl_domains(self) -> List[str]:
        """Extract all SSL-enabled domains from nginx config.

        Returns:
            List of unique domain names from SSL server blocks.
            Filters out: localhost, _, wildcards (*.example.com),
            IP addresses, and non-FQDN values.
        """
        structure = self.get_structure()
        domains = set()

        for server in structure.get('servers', []):
            # Only process SSL-enabled server blocks
            if not server.get('is_ssl'):
                continue

            for domain in server.get('domains', []):
                # Skip non-domain values
                if not domain or domain == '_' or domain == 'localhost':
                    continue
                # Skip wildcards (can't SSL check *.example.com)
                if domain.startswith('*.'):
                    continue
                # Skip IP addresses
                if re.match(r'^\d+\.\d+\.\d+\.\d+$', domain):
                    continue
                # Skip non-FQDN (no dot)
                if '.' not in domain:
                    continue
                domains.add(domain)

        return sorted(domains)

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
