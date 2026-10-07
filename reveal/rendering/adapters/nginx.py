"""Text bodies for nginx:// results; format, diagnostics and the exit code use the shared boundary."""

from typing import Any, Dict, List

from ..base import TypeDispatchRenderer
from ...adapters.ssl.probe import probe_text_lines


def _body(lines: List[str]) -> str:
    return '\n'.join(lines) + '\n'


def _next_steps(result: dict, header: bool = False, rule: bool = False) -> List[str]:
    """The result's next steps; `header` adds the 'Next Steps:' title, `rule` a dash rule."""
    steps = result.get('next_steps')
    if not steps:
        return []
    lines = ["-" * 60] if rule else []
    if header:
        lines.append("Next Steps:")
    return lines + [f"  • {step}" for step in steps]


def _ports(ports: list) -> List[str]:
    lines = ["Ports:"]
    if not ports:
        return lines + ["  (no listen directives found)"]
    for p in ports:
        port = p.get('port', '?')
        if p.get('is_ssl'):
            ssl_note = ' (certbot-managed)' if p.get('certbot_managed') else ''
            lines.append(f"  HTTPS ({port}): ✅ ssl{ssl_note}")
        else:
            redir = ' → redirect to HTTPS' if p.get('redirect_to_https') else ''
            lines.append(f"  HTTP  ({port}): ✅{redir}")
    return lines


def _upstream_server_line(srv: str, reach: dict) -> str:
    """One upstream server line with reachability status."""
    reachable = reach.get('reachable')
    icon = '✅' if reachable else ('❌' if reachable is False else '?')
    status = 'reachable' if reachable else 'unreachable'
    error = f" — {reach['error']}" if not reachable and reach.get('error') else ''
    return f"  server {srv}    {icon} {status}{error}"


def _upstreams(upstreams: dict) -> List[str]:
    if not upstreams:
        return ["Upstream: (no proxy_pass found)"]
    lines: List[str] = []
    for name, data in upstreams.items():
        lines.append(f"Upstream: {name}")
        reach_list = data.get('reachability', [])
        defn = data.get('definition', {})
        servers = defn.get('servers', []) if defn else []
        if not servers and reach_list:
            servers = [r['address'] for r in reach_list]
        for i, srv in enumerate(servers):
            reach = reach_list[i] if i < len(reach_list) else {}
            lines.append(_upstream_server_line(srv, reach))
        found_in = defn.get('found_in') if defn else None
        if found_in:
            lines.append(f"  (defined in {found_in})")
        elif defn and defn.get('raw') is None:
            lines.append("  ⚠️  definition not found")
    return lines


def _auth(auth: dict) -> List[str]:
    ab = auth.get('auth_basic')
    ar = auth.get('auth_request')
    locs = auth.get('locations_with_auth', [])
    if not ab and not ar and not locs:
        return ["Auth: none"]
    lines: List[str] = []
    if ab:
        lines.append(f"Auth: auth_basic \"{ab}\"")
    if ar:
        lines.append(f"Auth: auth_request {ar}")
    for loc in locs:
        if loc.get('auth_basic'):
            lines.append(f"  {loc['path']}: auth_basic \"{loc['auth_basic']}\"")
        if loc.get('auth_request'):
            lines.append(f"  {loc['path']}: auth_request {loc['auth_request']}")
    return lines


_LOCATION_TYPE_LABELS = {'proxy': '→ proxy', 'static': '→ static', 'alias': '→ alias',
                         'return': '→ return', 'other': ''}


def _locations(locations: list) -> List[str]:
    lines = ["Locations:"]
    if not locations:
        return lines + ["  (no location blocks found)"]
    for loc in locations:
        path = loc.get('path', '?')
        target = loc.get('target', '')
        auth_note = ''
        if 'auth_basic' in loc:
            auth_note = ' (auth_basic)' if loc['auth_basic'] else ' (auth off)'
        type_label = _LOCATION_TYPE_LABELS.get(loc.get('type', ''), '')
        target_str = f" {type_label} {target}" if target else ''
        lines.append(f"  {path:<30}{target_str}{auth_note}")
    return lines


def _fleet_header(site_count: int, date: str, nginx_conf) -> List[str]:
    lines = [f"\nFleet Audit — ({site_count} sites, {date})\n"]
    if nginx_conf:
        lines.append(f"  nginx.conf: {nginx_conf}")
    else:
        lines.append("  nginx.conf: not found — global column unavailable")
    return lines + [""]


_SEVERITY_ORDER = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'INFO': 3}


def _is_gap(entry: dict) -> bool:
    if entry.get('deprecated', False):
        return bool(entry['sites_with'] > 0)
    return bool(entry['sites_without'] > 0)


def _fleet_matrix_rows(matrix: list, only_failures: bool) -> List[str]:
    col_directive = max(max(len(e['label']) for e in matrix), len('Directive'))
    header = (f"  {'Directive':<{col_directive}}  {'Global':^6}"
              f"  {'With':>5}  {'Without':>7}  Action")
    lines = [header, "  " + "─" * (len(header) - 2)]
    printed = 0
    for entry in sorted(matrix, key=lambda e: (_SEVERITY_ORDER.get(e['severity'], 9), e['label'])):
        if only_failures and not _is_gap(entry):
            continue
        global_present = entry.get('global_present')
        if global_present is None:
            global_col = '  —   '
        elif global_present:
            global_col = '  ✅  '
        else:
            global_col = '  ❌  '
        without_col = f'{"—":>7}' if entry.get('deprecated', False) else f"{entry['sites_without']:>7}"
        consol_marker = ' ↑' if entry.get('consolidation_opportunity', False) else ''
        lines.append(f"  {entry['label']:<{col_directive}}  {global_col}  {entry['sites_with']:>5}"
                     f"  {without_col}  {entry.get('action', '')}{consol_marker}")
        printed += 1
    if only_failures and printed == 0:
        lines.append("  ✅ No gaps found.")
    return lines + [""]


def _consolidation_summary(matrix: list) -> List[str]:
    consol_entries = [e for e in matrix if e.get('consolidation_opportunity')]
    if not consol_entries:
        return []
    directives = ', '.join(e['label'] for e in consol_entries)
    return [f"  ↑ Consolidation: {directives}",
            "    Move these to nginx.conf http{} — one change fixes all sites.",
            ""]


def _snippet_consistency(snippets: list) -> List[str]:
    if not snippets:
        return []
    lines = ["  Snippet Consistency:"]
    for snip in snippets:
        swo = snip['sites_without']
        missing = snip.get('missing_from', [])
        lines.append(f"    {snip['snippet']}  — included by {snip['sites_with']}, missing from {swo}")
        if missing and swo > 0:
            extra = f' (+{len(missing) - 6} more)' if len(missing) > 6 else ''
            lines.append(f"       Missing from: {', '.join(missing[:6])}{extra}")
    return lines + [""]


class NginxRenderer(TypeDispatchRenderer):
    """Renders NginxUriAdapter results as text bodies, one `_render_<type>` per result type."""

    @classmethod
    def _failure_detail(cls, result: Dict[str, Any]) -> List[str]:
        """Detail under the router's error line, on stderr with it (BACK-1523, BACK-1553)."""
        lines = []
        if result.get('config_file'):
            lines.append(f"  Config file: {result['config_file']}")
        if result.get('note'):
            lines.append(f"  Note: {result['note']}")
        searched = result.get('searched', [])
        if searched:
            lines.append("  Searched:")
            lines.extend(f"    • {d}" for d in searched)
        return lines

    @classmethod
    def exit_code(cls, result: Dict[str, Any], format: str = 'text') -> int:
        """A fleet audit with gaps exits 2 in text; --format json has always exited 0
        (BACK-1758 decides whether it should not)."""
        if format != 'json' and result.get('type') == 'nginx_fleet_audit' and result.get('has_gaps'):
            return 2
        return 0

    @classmethod
    def _render_nginx_sites_overview(cls, result: dict) -> str:
        sites = result.get('sites', [])
        lines = [f"\nNginx Sites Overview — {len(sites)} configs found\n"]
        if not sites:
            lines.append("  No nginx config files found in standard locations.")
        for site in sites:
            enabled = '✅' if site.get('enabled') else '❌'
            symlink = ' → symlink' if site.get('is_symlink') else ''
            domains = ', '.join(site.get('domains', [])[:4])
            extra = f" (+{len(site['domains']) - 4} more)" if len(site.get('domains', [])) > 4 else ''
            lines.append(f"  {enabled} {site['file']}{symlink}")
            if domains:
                lines.append(f"       {domains}{extra}")
        artifact_files = result.get('artifact_files', [])
        if artifact_files:
            lines.extend(["", f"  ⚠️  {len(artifact_files)} backup/temp file(s) found (not loaded by nginx):"])
            lines.extend(f"     {f}" for f in artifact_files[:10])
            if len(artifact_files) > 10:
                lines.append(f"     ... and {len(artifact_files) - 10} more")
        lines.append("")
        return _body(lines + _next_steps(result, header=True))

    @classmethod
    def _render_nginx_vhost_summary(cls, result: dict) -> str:
        symlink = result.get('symlink', {})
        rule = '=' * 60
        lines = [f"\n{rule}", f"Nginx Vhost: {result.get('domain', '?')}", f"{rule}\n",
                 f"Config file: {result.get('config_file', '?')}"]
        if symlink.get('is_symlink'):
            ok = '✅' if symlink.get('exists') else '❌'
            lines.append(f"Symlinked:   {ok} → {symlink.get('target', '?')}")
        # BACK-259: co-hosted names in the same config file
        if result.get('also_serves'):
            lines.append(f"Also serves: {', '.join(result['also_serves'])}")
        lines.append("")
        for section in (_ports(result.get('ports', [])),
                        _upstreams(result.get('upstreams', {})),
                        _auth(result.get('auth', {})),
                        _locations(result.get('locations', []))):
            lines.extend(section + [""])
        warnings = result.get('warnings', [])
        if warnings:
            lines.append("⚠️  Warnings:")
            lines.extend(f"  • {w}" for w in warnings)
            lines.append("")
        if result.get('http_probe'):  # --probe
            lines.extend([""] + probe_text_lines(result['http_probe']) + [""])
        return _body(lines + _next_steps(result, header=True, rule=True))

    @classmethod
    def _render_nginx_vhost_ports(cls, result: dict) -> str:
        lines = [f"\nPorts — {result.get('domain', '?')}\n"] + _ports(result.get('ports', [])) + [""]
        return _body(lines + _next_steps(result))

    @classmethod
    def _render_nginx_vhost_upstream(cls, result: dict) -> str:
        lines = ([f"\nUpstream Health — {result.get('domain', '?')}\n"]
                 + _upstreams(result.get('upstreams', {})) + [""])
        return _body(lines + _next_steps(result))

    @classmethod
    def _render_nginx_vhost_auth(cls, result: dict) -> str:
        lines = [f"\nAuth Directives — {result.get('domain', '?')}\n"] + _auth(result.get('auth', {})) + [""]
        return _body(lines + _next_steps(result))

    @classmethod
    def _render_nginx_vhost_locations(cls, result: dict) -> str:
        lines = ([f"\nLocation Blocks — {result.get('domain', '?')}\n"]
                 + _locations(result.get('locations', [])) + [""])
        return _body(lines + _next_steps(result))

    @classmethod
    def _render_nginx_vhost_config(cls, result: dict) -> str:
        lines = [f"\nNginx Config — {result.get('domain', '?')}  [{result.get('config_file', '?')}]\n",
                 result.get('server_block', ''), ""]
        return _body(lines + _next_steps(result, rule=True))

    @classmethod
    def _render_nginx_fleet_audit(cls, result: dict) -> str:
        matrix = result.get('matrix', [])
        lines = _fleet_header(result.get('site_count', 0), result.get('date', ''), result.get('nginx_conf'))
        if result.get('nginx_conf_error'):
            lines.append(f"  ⚠ nginx.conf not audited ({result['nginx_conf_error']}): "
                         "global directives are not checked")
        if not matrix:
            return _body(lines + ["  No site configs found."])
        lines.extend(_fleet_matrix_rows(matrix, result.get('only_failures', False)))
        lines.extend(_consolidation_summary(matrix))
        lines.extend(_snippet_consistency(result.get('snippet_consistency', [])))
        return _body(lines)
