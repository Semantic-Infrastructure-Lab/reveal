"""Renderer for nginx:// URI adapter results."""

import sys

from reveal.rendering import TypeDispatchRenderer


class NginxUriRenderer(TypeDispatchRenderer):
    """Renderer for NginxUriAdapter results."""

    _ICONS = {'ok': '✅', 'warn': '⚠️ ', 'err': '❌', 'info': 'ℹ️ '}

    @staticmethod
    def _render_nginx_sites_overview(result: dict) -> None:
        sites = result.get('sites', [])
        print(f"\nNginx Sites Overview — {len(sites)} configs found\n")
        if not sites:
            print("  No nginx config files found in standard locations.")
        for site in sites:
            enabled = '✅' if site.get('enabled') else '❌'
            symlink = ' → symlink' if site.get('is_symlink') else ''
            domains = ', '.join(site.get('domains', [])[:4])
            extra = f" (+{len(site['domains']) - 4} more)" if len(site.get('domains', [])) > 4 else ''
            print(f"  {enabled} {site['file']}{symlink}")
            if domains:
                print(f"       {domains}{extra}")
        artifact_files = result.get('artifact_files', [])
        if artifact_files:
            print()
            print(f"  ⚠️  {len(artifact_files)} backup/temp file(s) found (not loaded by nginx):")
            for f in artifact_files[:10]:
                print(f"     {f}")
            if len(artifact_files) > 10:
                print(f"     ... and {len(artifact_files) - 10} more")
        print()
        if result.get('next_steps'):
            print("Next Steps:")
            for step in result['next_steps']:
                print(f"  • {step}")

    @staticmethod
    def _render_nginx_vhost_not_found(result: dict) -> None:
        domain = result.get('domain', '?')
        print(f"\n❌ No nginx config found for: {domain}\n")
        if result.get('config_file'):
            print(f"  Config file: {result['config_file']}")
        if result.get('note'):
            print(f"  Note: {result['note']}")
        searched = result.get('searched', [])
        if searched:
            print(f"\n  Searched:")
            for d in searched:
                print(f"    • {d}")
        if result.get('next_steps'):
            print()
            for step in result['next_steps']:
                print(f"  • {step}")

    @staticmethod
    def _print_ports(ports: list) -> None:
        print("Ports:")
        if not ports:
            print("  (no listen directives found)")
            return
        for p in ports:
            port = p.get('port', '?')
            spec = p.get('spec', port)
            if p.get('is_ssl'):
                ssl_note = ' (certbot-managed)' if p.get('certbot_managed') else ''
                print(f"  HTTPS ({port}): ✅ ssl{ssl_note}")
            else:
                redir = ' → redirect to HTTPS' if p.get('redirect_to_https') else ''
                print(f"  HTTP  ({port}): ✅{redir}")

    @staticmethod
    def _format_upstream_server_line(srv: str, reach: dict) -> str:
        """Format one upstream server line with reachability status."""
        reachable = reach.get('reachable')
        icon = '✅' if reachable else ('❌' if reachable is False else '?')
        status = 'reachable' if reachable else 'unreachable'
        error = f" — {reach['error']}" if not reachable and reach.get('error') else ''
        return f"  server {srv}    {icon} {status}{error}"

    @staticmethod
    def _print_upstreams(upstreams: dict) -> None:
        if not upstreams:
            print("Upstream: (no proxy_pass found)")
            return
        for name, data in upstreams.items():
            print(f"Upstream: {name}")
            reach_list = data.get('reachability', [])
            defn = data.get('definition', {})
            servers = defn.get('servers', []) if defn else []
            if not servers and reach_list:
                servers = [r['address'] for r in reach_list]
            for i, srv in enumerate(servers):
                reach = reach_list[i] if i < len(reach_list) else {}
                print(NginxUriRenderer._format_upstream_server_line(srv, reach))
            found_in = defn.get('found_in') if defn else None
            if found_in:
                print(f"  (defined in {found_in})")
            elif defn and defn.get('raw') is None:
                print("  ⚠️  definition not found")

    @staticmethod
    def _print_auth(auth: dict) -> None:
        ab = auth.get('auth_basic')
        ar = auth.get('auth_request')
        locs = auth.get('locations_with_auth', [])
        if not ab and not ar and not locs:
            print("Auth: none")
            return
        if ab:
            print(f"Auth: auth_basic \"{ab}\"")
        if ar:
            print(f"Auth: auth_request {ar}")
        for loc in locs:
            loc_ab = loc.get('auth_basic')
            loc_ar = loc.get('auth_request')
            if loc_ab:
                print(f"  {loc['path']}: auth_basic \"{loc_ab}\"")
            if loc_ar:
                print(f"  {loc['path']}: auth_request {loc_ar}")

    @staticmethod
    def _print_locations(locations: list) -> None:
        print("Locations:")
        if not locations:
            print("  (no location blocks found)")
            return
        for loc in locations:
            path = loc.get('path', '?')
            target = loc.get('target', '')
            loc_type = loc.get('type', '')
            auth_note = ''
            if 'auth_basic' in loc:
                auth_note = ' (auth_basic)' if loc['auth_basic'] else ' (auth off)'
            type_label = {'proxy': '→ proxy', 'static': '→ static', 'alias': '→ alias',
                          'return': '→ return', 'other': ''}.get(loc_type, '')
            target_str = f" {type_label} {target}" if target else ''
            print(f"  {path:<30}{target_str}{auth_note}")

    @staticmethod
    def _render_nginx_vhost_summary(result: dict) -> None:
        domain = result.get('domain', '?')
        config_file = result.get('config_file', '?')
        symlink = result.get('symlink', {})

        print(f"\n{'='*60}")
        print(f"Nginx Vhost: {domain}")
        print(f"{'='*60}\n")

        # Config file + symlink
        if symlink.get('is_symlink'):
            target = symlink.get('target', '?')
            ok = '✅' if symlink.get('exists') else '❌'
            print(f"Config file: {config_file}")
            print(f"Symlinked:   {ok} → {target}")
        else:
            print(f"Config file: {config_file}")

        # BACK-259: co-hosted names in the same config file
        also_serves = result.get('also_serves')
        if also_serves:
            print(f"Also serves: {', '.join(also_serves)}")
        print()

        # Ports
        NginxUriRenderer._print_ports(result.get('ports', []))
        print()

        # Upstreams
        NginxUriRenderer._print_upstreams(result.get('upstreams', {}))
        print()

        # Auth
        NginxUriRenderer._print_auth(result.get('auth', {}))
        print()

        # Locations
        NginxUriRenderer._print_locations(result.get('locations', []))
        print()

        # Warnings
        warnings = result.get('warnings', [])
        if warnings:
            print("⚠️  Warnings:")
            for w in warnings:
                print(f"  • {w}")
            print()

        # HTTP probe (--probe)
        if result.get('http_probe'):
            print()
            from ..ssl.probe import render_probe_text
            render_probe_text(result['http_probe'])
            print()

        # Next steps
        if result.get('next_steps'):
            print(f"{'-'*60}")
            print("Next Steps:")
            for step in result['next_steps']:
                print(f"  • {step}")

    @staticmethod
    def _render_nginx_vhost_ports(result: dict) -> None:
        domain = result.get('domain', '?')
        print(f"\nPorts — {domain}\n")
        NginxUriRenderer._print_ports(result.get('ports', []))
        print()
        if result.get('next_steps'):
            for step in result['next_steps']:
                print(f"  • {step}")

    @staticmethod
    def _render_nginx_vhost_upstream(result: dict) -> None:
        domain = result.get('domain', '?')
        print(f"\nUpstream Health — {domain}\n")
        NginxUriRenderer._print_upstreams(result.get('upstreams', {}))
        print()
        if result.get('next_steps'):
            for step in result['next_steps']:
                print(f"  • {step}")

    @staticmethod
    def _render_nginx_vhost_auth(result: dict) -> None:
        domain = result.get('domain', '?')
        print(f"\nAuth Directives — {domain}\n")
        NginxUriRenderer._print_auth(result.get('auth', {}))
        print()
        if result.get('next_steps'):
            for step in result['next_steps']:
                print(f"  • {step}")

    @staticmethod
    def _render_nginx_vhost_locations(result: dict) -> None:
        domain = result.get('domain', '?')
        print(f"\nLocation Blocks — {domain}\n")
        NginxUriRenderer._print_locations(result.get('locations', []))
        print()
        if result.get('next_steps'):
            for step in result['next_steps']:
                print(f"  • {step}")

    @staticmethod
    def _render_nginx_vhost_config(result: dict) -> None:
        domain = result.get('domain', '?')
        config_file = result.get('config_file', '?')
        server_block = result.get('server_block', '')
        print(f"\nNginx Config — {domain}  [{config_file}]\n")
        print(server_block)
        print()
        if result.get('next_steps'):
            print(f"{'-'*60}")
            for step in result['next_steps']:
                print(f"  • {step}")

    @staticmethod
    def _render_nginx_fleet_audit(result: dict) -> None:
        site_count = result.get('site_count', 0)
        date = result.get('date', '')
        matrix = result.get('matrix', [])
        snippets = result.get('snippet_consistency', [])
        nginx_conf = result.get('nginx_conf')
        only_failures = result.get('only_failures', False)
        has_gaps = result.get('has_gaps', False)

        print(f"\nFleet Audit — ({site_count} sites, {date})\n")
        if nginx_conf:
            print(f"  nginx.conf: {nginx_conf}")
        else:
            print("  nginx.conf: not found — global column unavailable")
        print()

        if not matrix:
            print("  No site configs found.")
            return

        # Column widths
        col_directive = max(len(e['label']) for e in matrix)
        col_directive = max(col_directive, len('Directive'))

        header = (f"  {'Directive':<{col_directive}}  {'Global':^6}"
                  f"  {'With':>5}  {'Without':>7}  Action")
        separator = "  " + "─" * (len(header) - 2)
        print(header)
        print(separator)

        _SEV_ORDER = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'INFO': 3}
        printed = 0
        for entry in sorted(matrix, key=lambda e: (_SEV_ORDER.get(e['severity'], 9), e['label'])):
            deprecated = entry.get('deprecated', False)
            global_present = entry.get('global_present')
            sites_with = entry['sites_with']
            sites_without = entry['sites_without']
            action = entry.get('action', '')
            consol = entry.get('consolidation_opportunity', False)

            # Skip passing checks in --only-failures mode
            if only_failures:
                is_gap = (not deprecated and sites_without > 0) or (deprecated and sites_with > 0)
                if not is_gap:
                    continue

            if global_present is None:
                global_col = '  —   '
            elif global_present:
                global_col = '  ✅  '
            else:
                global_col = '  ❌  '

            with_col = f'{sites_with:>5}'
            without_col = f'{"—":>7}' if deprecated else f'{sites_without:>7}'
            consol_marker = ' ↑' if consol else ''
            print(f"  {entry['label']:<{col_directive}}  {global_col}  {with_col}  {without_col}  {action}{consol_marker}")
            printed += 1

        if only_failures and printed == 0:
            print("  ✅ No gaps found.")

        print()

        # Consolidation opportunities summary
        consol_entries = [e for e in matrix if e.get('consolidation_opportunity')]
        if consol_entries:
            directives = ', '.join(e['label'] for e in consol_entries)
            print(f"  ↑ Consolidation: {directives}")
            print("    Move these to nginx.conf http{} — one change fixes all sites.")
            print()

        # Snippet consistency
        if snippets:
            print("  Snippet Consistency:")
            for snip in snippets:
                sw = snip['sites_with']
                swo = snip['sites_without']
                missing = snip.get('missing_from', [])
                print(f"    {snip['snippet']}  — included by {sw}, missing from {swo}")
                if missing and swo > 0:
                    missing_str = ', '.join(missing[:6])
                    extra = f' (+{len(missing) - 6} more)' if len(missing) > 6 else ''
                    print(f"       Missing from: {missing_str}{extra}")
            print()

        if has_gaps:
            sys.exit(2)

    @staticmethod
    def render_error(error: Exception) -> None:
        msg = str(error)
        if 'Unknown element' in msg:
            print(f"Error: {msg}", file=sys.stderr)
            print("", file=sys.stderr)
            print("Available elements: ports, upstream, auth, locations, config", file=sys.stderr)
        else:
            print(f"Error: {error}", file=sys.stderr)
