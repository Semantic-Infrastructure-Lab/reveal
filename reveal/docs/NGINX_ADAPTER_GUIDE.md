---
title: nginx:// Adapter Guide
category: adapter-guide
adapter: nginx
stability: beta
---
# nginx:// Adapter Guide

**Protocol**: `nginx://`
**Stability**: 🟡 Beta
**Purpose**: Domain-centric nginx vhost inspection — find the config for a domain and get structured data without touching files directly
**See Also**: [NGINX_ANALYZER_GUIDE.md](NGINX_ANALYZER_GUIDE.md) — file-based nginx analysis (N001–N007 rules)

---

## Overview

The `nginx://` adapter looks up the nginx configuration that handles a given domain and returns structured information: ports, upstreams, auth directives, location blocks, and symlink status.

This is the complement to file-based analysis. Instead of finding the right file yourself, you give reveal a domain name and it resolves the config automatically.

```bash
reveal nginx://example.com          # Full vhost summary
reveal nginx://                     # Overview of all enabled sites
```

**Searches**: `/etc/nginx/sites-enabled/` (extension-less files) and `/etc/nginx/conf.d/` (`*.conf` files). Both symlinks and regular files are handled.

---

## URI Syntax

```
nginx://<domain>[/<element>]
nginx://
```

| Form | Description |
|------|-------------|
| `nginx://` | Overview: list all enabled sites |
| `nginx://example.com` | Full vhost summary for example.com |
| `nginx://example.com/ports` | Listening ports only |
| `nginx://example.com/upstream` | proxy_pass targets + TCP reachability |
| `nginx://example.com/auth` | auth_basic and auth_request directives |
| `nginx://example.com/locations` | All location blocks |
| `nginx://example.com/config` | Raw server block(s) for this domain |

---

## Quick Examples

```bash
# Vhost summary — config file, ports, upstream, auth, locations
reveal nginx://smd-ops.mytia.net

# All enabled sites
reveal nginx://

# Just the ports (SSL on? redirect-to-https?)
reveal nginx://smd-ops.mytia.net/ports

# Upstream reachability — is the backend actually listening?
reveal nginx://smd-ops.mytia.net/upstream

# Auth check — is auth_basic on or off?
reveal nginx://smd-ops.mytia.net/auth

# All location blocks — what gets routed where?
reveal nginx://smd-ops.mytia.net/locations

# Raw config — see the actual server block
reveal nginx://smd-ops.mytia.net/config
```

---

## Example Output

### `reveal nginx://smd-ops.mytia.net`

```
nginx://smd-ops.mytia.net

Config: /etc/nginx/sites-enabled/smd-ops.mytia.net
  Symlink: → /etc/nginx/sites-available/smd-ops.mytia.net

Ports:
  80   HTTP  → redirect to https
  443  HTTPS  ssl_certificate /etc/nginx/ssl/smd-ops.mytia.net.crt

Upstream: backend (proxy_pass http://127.0.0.1:8080)
  127.0.0.1:8080  ✅ reachable (3ms)

Auth:
  None

Locations (3):
  /.well-known/acme-challenge/  root /home/smd/public_html
  /static/                      root /home/smd/app/static
  /                             proxy_pass http://backend
```

### `reveal nginx://`

```
nginx:// — Enabled Sites (44 sites)

  File                                          Domains                       Symlink
  ──────────────────────────────────────────────────────────────────────────────────
  sites-enabled/smd-ops.mytia.net               smd-ops.mytia.net             → sites-available/
  sites-enabled/frono.mytia.net                 frono.mytia.net               → sites-available/
  conf.d/default.conf                           _                             (regular file)
  ...
```

---

## Workflows

### After nginx config change

```bash
reveal nginx://smd-ops.mytia.net            # verify config was applied
reveal nginx://smd-ops.mytia.net/ports      # check SSL block is present
reveal nginx://smd-ops.mytia.net/upstream   # verify upstream still reachable
reveal ssl://smd-ops.mytia.net --check      # verify SSL cert intact
```

### Diagnose unexpected redirect

```bash
reveal nginx://smd-ops.mytia.net            # see all location blocks at once
reveal nginx://smd-ops.mytia.net/locations  # inspect location targets
reveal domain://smd-ops.mytia.net --check   # verify DNS + HTTP response
```

### Auth audit

```bash
reveal nginx://smd-ops.mytia.net/auth       # check auth_basic on/off
reveal nginx://smd-ops.mytia.net/config     # view raw config to verify
```

---

## Anti-Patterns

| Instead of... | Use... | Why |
|---------------|--------|-----|
| `ssh server 'nginx -T \| grep -B2 -A5 domain'` | `reveal nginx://domain` | One command, structured output |
| `ssh server 'cat /etc/nginx/sites-enabled/domain'` | `reveal nginx://domain` | Finds the file automatically |
| `ssh server 'ls -la /etc/nginx/sites-enabled/domain'` | `reveal nginx://domain` | Symlink status included in vhost summary |
| `reveal /etc/nginx/sites-enabled/domain.conf` | `reveal nginx://domain` | No need to know the filename |

---

## Notes

- **Upstream reachability** checks TCP connectivity only (3s timeout) — not HTTP response codes
- **Remote servers**: nginx:// only works locally. For SSH-accessed nginx, use file-path form: `reveal /etc/nginx/conf.d/file.conf --check`
- **SSL cert status**: `reveal ssl://domain --check` — nginx:// doesn't check cert validity, only config structure
- **Running N001–N007 rules**: use `reveal /path/to/nginx.conf --check`, not `nginx://`

---

## JSON Output

```bash
reveal nginx://example.com --format=json
```

Returns a structured object with `config_file`, `symlink`, `ports`, `upstream`, `auth`, `locations` keys — suitable for scripting.

---

## Related Guides

- [NGINX_ANALYZER_GUIDE.md](NGINX_ANALYZER_GUIDE.md) — file-based analysis, N001–N007 rules, `--check-acl`, `--validate-nginx-acme`
- [SSL_ADAPTER_GUIDE.md](SSL_ADAPTER_GUIDE.md) — live SSL certificate inspection
- [DOMAIN_ADAPTER_GUIDE.md](DOMAIN_ADAPTER_GUIDE.md) — DNS + HTTP health checks
- [CPANEL_ADAPTER_GUIDE.md](CPANEL_ADAPTER_GUIDE.md) — cPanel user environment

```bash
reveal help://nginx     # inline help (file-based analysis)
reveal help://ssl       # SSL adapter
reveal help://domain    # domain adapter
```
