"""Renderer for nginx:// URI adapter results."""

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
                reachable = reach.get('reachable')
                icon = '✅' if reachable else ('❌' if reachable is False else '?')
                error = f" — {reach['error']}" if not reachable and reach.get('error') else ''
                print(f"  server {srv}    {icon} {'reachable' if reachable else 'unreachable'}{error}")

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
            print(f"Symlinked:   {ok} → {target}\n")
        else:
            print(f"Config file: {config_file}\n")

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
    def render_error(error: Exception) -> None:
        import sys
        msg = str(error)
        if 'Unknown element' in msg:
            print(f"Error: {msg}", file=sys.stderr)
            print("", file=sys.stderr)
            print("Available elements: ports, upstream, auth, locations, config", file=sys.stderr)
        else:
            print(f"Error: {error}", file=sys.stderr)
