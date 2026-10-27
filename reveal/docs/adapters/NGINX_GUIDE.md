---
title: nginx Guide
category: guide
---
# nginx Guide

Reveal provides two complementary ways to work with nginx:

- **`nginx://` adapter** — domain-centric vhost inspection via URI. Give reveal a domain name; it finds the config automatically.
- **nginx file analyzer** — static analysis of nginx config files. Run quality rules (N001–N012), ACME/SSL audits, and operator diagnostics.

---

## Part 1: nginx:// URI Adapter

**Protocol**: `nginx://`
**Stability**: 🟡 Beta
**Purpose**: Domain-centric nginx vhost inspection — find the config for a domain and get structured data without touching files directly

---

### Overview

The `nginx://` adapter looks up the nginx configuration that handles a given domain and returns structured information: ports, upstreams, auth directives, location blocks, and symlink status.

This is the complement to file-based analysis. Instead of finding the right file yourself, you give reveal a domain name and it resolves the config automatically.

```bash
reveal nginx://example.com          # Full vhost summary
reveal nginx://                     # Overview of all enabled sites
```

**Searches**: `/etc/nginx/sites-enabled/` (all files), `/etc/nginx/conf.d/` (`*.conf`, plus one subdirectory level such as `conf.d/users/`), and `/usr/local/nginx/conf/sites-enabled/` and `/usr/local/etc/nginx/sites-enabled/`. Backup files (`.bak`, `.backup`, `.old`, `.disabled`, `.orig`, `~`) are skipped. Both symlinks and regular files are handled.

---

### URI Syntax

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

### Quick Examples

```bash
# Vhost summary — config file, ports, upstream, auth, locations
reveal nginx://app.example.com

# All enabled sites
reveal nginx://

# Just the ports (SSL on? redirect-to-https?)
reveal nginx://app.example.com/ports

# Upstream reachability — is the backend actually listening?
reveal nginx://app.example.com/upstream

# Auth check — is auth_basic on or off?
reveal nginx://app.example.com/auth

# All location blocks — what gets routed where?
reveal nginx://app.example.com/locations

# Raw config — see the actual server block
reveal nginx://app.example.com/config
```

---

### Example Output

#### `reveal nginx://app.example.com`

```
============================================================
Nginx Vhost: app.example.com
============================================================

Config file: /etc/nginx/sites-enabled/app.example.com
Symlinked:   ✅ → /etc/nginx/sites-available/app.example.com

Ports:
  HTTP  (80): ✅ → redirect to HTTPS
  HTTPS (443): ✅ ssl

Upstream: backend
  server 127.0.0.1:59998    ❌ unreachable — [Errno 111] Connection refused

Auth: none

Locations:
  /.well-known/acme-challenge/   → static /home/appuser/public_html
  /                              → return 301 https://$host$request_uri
  /.well-known/acme-challenge/   → static /home/appuser/public_html
  /static/                       → static /home/appuser/app/static
  /                              → proxy http://backend

⚠️  Warnings:
  • Upstream 'backend' server 127.0.0.1:59998 is not reachable: [Errno 111] Connection refused

------------------------------------------------------------
Next Steps:
  • reveal nginx://app.example.com/upstream  # upstream health detail
  • reveal nginx://app.example.com/config    # full compiled config
  • reveal ssl://app.example.com --check     # cert detail
```

Locations lists every server block that names the domain (here both the port-80 redirect block and the 443 block).

#### `reveal nginx://`

```
Nginx Sites Overview — 2 configs found

  ✅ /etc/nginx/sites-enabled/app.example.com → symlink
       app.example.com, www.app.example.com
  ✅ /etc/nginx/conf.d/default.conf

Next Steps:
  • Inspect a specific domain: reveal nginx://DOMAIN
  • Check SSL certs across all nginx: reveal 'ssl://nginx:///etc/nginx/conf.d/*.conf' --check
```

A catch-all `server_name _` block shows no domain line.

---

### Workflows

#### After nginx config change

```bash
reveal nginx://app.example.com            # verify config was applied
reveal nginx://app.example.com/ports      # check SSL block is present
reveal nginx://app.example.com/upstream   # verify upstream still reachable
reveal ssl://app.example.com --check      # verify SSL cert intact
```

#### Diagnose unexpected redirect

```bash
reveal nginx://app.example.com            # see all location blocks at once
reveal nginx://app.example.com/locations  # inspect location targets
reveal domain://app.example.com --check   # verify DNS + HTTP response
```

#### Auth audit

```bash
reveal nginx://app.example.com/auth       # check auth_basic on/off
reveal nginx://app.example.com/config     # view raw config to verify
```

---

### Anti-Patterns

| Instead of... | Use... | Why |
|---------------|--------|-----|
| `ssh server 'nginx -T \| grep -B2 -A5 domain'` | `reveal nginx://domain` | One command, structured output |
| `ssh server 'cat /etc/nginx/sites-enabled/domain'` | `reveal nginx://domain` | Finds the file automatically |
| `ssh server 'ls -la /etc/nginx/sites-enabled/domain'` | `reveal nginx://domain` | Symlink status included in vhost summary |
| `reveal /etc/nginx/sites-enabled/domain.conf` | `reveal nginx://domain` | No need to know the filename |

---

### Notes

- **Upstream reachability** checks TCP connectivity only (3s timeout) — not HTTP response codes
- **Remote servers**: nginx:// only works locally. For SSH-accessed nginx, use file-path form: `reveal check /etc/nginx/conf.d/file.conf`
- **SSL cert status**: `reveal ssl://domain --check` — nginx:// doesn't check cert validity, only config structure
- **Running N001–N012 rules**: use `reveal check /path/to/nginx.conf`, not `nginx://`. Use `--select N004` to focus on one rule; `--ignore N011,E501` to suppress noise rules.

---

### Fleet Audit (`--audit`)

`reveal nginx:// --audit` reads all enabled site configs and `nginx.conf` then produces a cross-site consistency matrix. It answers "how many of our 46 sites are missing X?" and surfaces whether a directive belongs in the global http{} block rather than scattered across individual vhosts.

```bash
reveal nginx:// --audit                    # full fleet consistency matrix
reveal nginx:// --audit --only-failures    # directives with gaps only
reveal nginx:// --audit --format json      # machine-readable
```

**Example output:**

```
Fleet Audit — (46 sites, 2026-03-19)

  nginx.conf: /etc/nginx/nginx.conf

  Directive                   Global    With  Without  Action
  ──────────────────────────────────────────────────────────────────────────────
  Strict-Transport-Security     ❌        0       46  Add to nginx.conf http{}
  X-Content-Type-Options        ❌       38        8  Move to nginx.conf http{} ↑
  X-Frame-Options               ❌       38        8  Move to nginx.conf http{} ↑
  server_tokens off             ❌       14       32  Move to nginx.conf http{}
  X-XSS-Protection (depr.)      —       38        —  Remove — deprecated since 2019, ignored by Chrome
  http2 on 443 listener         —       21       25  Add per-site (certbot strips http2 on renewal)
  limit_req applied             —        1       45  Add zones to nginx.conf, then limit_req per sensitive location

  ↑ Consolidation: X-Content-Type-Options, X-Frame-Options
    Move these to nginx.conf http{} — one change fixes all sites.

  Snippet Consistency:
    snippets/security-headers.conf  — included by 38, missing from 8
       Missing from: api.example.com, motion.example.com, ...
```

**Exit codes:** fleet audits exit 2 when gaps are found and 0 when clean, in both text and JSON. A failed request exits 1. `Snippet Consistency` appears only when sites include snippets.

JSON (`--format json`) has `type: nginx_fleet_audit` and a `matrix` list whose entries carry `id`, `label`, `severity`, `global_present`, `deprecated`, `sites_with`, `sites_without`, `sites_with_names`, `sites_without_names`, `consolidation_opportunity` and `action`.

**Consolidation hint**: when a directive appears in ≥50% of site configs but is absent from nginx.conf http{}, it's marked with `↑` as a consolidation opportunity — one line in nginx.conf fixes the whole fleet.

**`X-XSS-Protection`** is a deprecated header check — "Sites With" means sites that *have* the deprecated header (should remove it). "Sites Without" is `—` because absence is the correct state.

---

### JSON Output

```bash
reveal nginx://example.com --format=json
```

Returns `type: nginx_vhost_summary` with `domain`, `config_file`, `symlink`, `ports`, `upstreams` (keyed by upstream name, each with `definition` and `reachability`), `auth`, `locations`, and `warnings` — suitable for scripting.

---

## Part 2: nginx Config File Analyzer

**Input**: nginx config files (`.conf`, `nginx.conf`)
**URI**: plain file paths — `reveal /path/to/nginx.conf`
**Stability**: 🟢 Stable (structure display, `--check`) / 🟡 Beta (operator commands)

---

### Overview

The nginx analyzer reads nginx configuration files and surfaces structure, rules, and operator-focused diagnostic commands. Unlike URI-scheme adapters, nginx is invoked with a plain file path:

```bash
reveal /etc/nginx/nginx.conf
reveal /etc/nginx/conf.d/users/myuser.conf
```

The analyzer covers two modes:
- **Structure display** — show servers, locations, upstreams, directives
- **Operator commands** — `--check`, `--check-acl`, `--validate-nginx-acme`, `--cpanel-certs`, `--diagnose`, and more

---

### Quick Start

```bash
# Show config structure
reveal /etc/nginx/conf.d/users/myuser.conf

# Run all nginx rules (N001–N012)
reveal check /etc/nginx/conf.d/users/myuser.conf

# Full ACME+ACL+SSL audit (the single command that catches most SSL renewal failures)
reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme

# Focus on one domain in a large multi-domain config
reveal /etc/nginx/conf.d/users/myuser.conf --server-name example.com
```

---

### Structure Display

Without flags, `reveal` shows the config's parsed structure:

```bash
reveal /etc/nginx/conf.d/users/myuser.conf
```

Surfaces:
- **Main directives** — `user`, `worker_processes`, `error_log`, `pid`, `ssl_protocols`, `ssl_ciphers`, `client_max_body_size`
- **http{} directives** — timeout, buffer, proxy settings at the http block level
- **events{} directives** — `worker_connections`, etc.
- **Server blocks** — `server_name`, `listen`, SSL cert paths, root
- **Location blocks** — `location`, `proxy_pass`, `root`, headers
- **Upstreams** — `server` entries with `max_fails`, `fail_timeout`, `keepalive`
- **Map blocks** — `map $src $target {}` (common in cPanel/WHM configs)

#### `--server-name` filter

Large cPanel user configs have one server block per domain — a 1,500-line file for 30 domains. `--server-name` filters output to just the server block(s) matching that `server_name` directive:

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --server-name shop.example.com
```

Matches the primary name and all aliases in the `server_name` directive. Essential for targeting a specific vhost in a dense config.

---

### Rule Checking (`--check`)

```bash
reveal check /etc/nginx/conf.d/users/myuser.conf

# Focus on ACME path issues only (useful on cPanel auto-generated configs)
reveal check /etc/nginx/conf.d/users/myuser.conf --select N004

# Suppress certbot-stripped http2 (N011) and line-length (E501) noise
reveal check /etc/nginx/conf.d/users/myuser.conf --ignore N011,E501
```

Runs the N001–N012 nginx rules against the config. Results are grouped when a rule fires many times in one file (configurable with `--no-group`). Each finding prints as `file:line:col <icon> CODE message`, followed by a `💡` fix line and usually a `📝` context line; the samples below show the first line.

#### N001 — Duplicate backends

Detects multiple `upstream` blocks pointing to the same `server:port`. A common copy-paste misconfiguration that can cause confusing traffic distribution.

```
myuser.conf:5:1 ❌ N001 Upstream 'app2' shares backend 127.0.0.1:8000 with 'app1'
```

#### N002 — SSL server missing certificate (CRITICAL)

Detects `listen 443 ssl` without `ssl_certificate` and `ssl_certificate_key`. The server will fail to start.

```
myuser.conf:37:1 🚨 N002 SSL server 'api.example.com' missing both ssl_certificate and ssl_certificate_key
```

#### N003 — Proxy location missing headers

Detects `proxy_pass` locations missing `X-Real-IP` or `X-Forwarded-For`. Without these, the upstream sees the nginx IP, not the real client IP.

```
myuser.conf:22:1 ⚠️  N003 Proxy location '~ \.php$' missing headers: X-Forwarded-For, X-Real-IP
```

#### N004 — ACME challenge path inconsistency (HIGH)

Detects server blocks with different `root` paths for `/.well-known/acme-challenge/` locations. Let's Encrypt uses one certbot/webroot directory — if some server blocks point elsewhere, renewal fails for those domains silently.

```
myuser.conf:31:1 ❌ N004 ACME challenge root '/home/olduser/public_html' differs from common path '/home/myuser/public_html' (1 server(s) affected)
```

**Context**: This pattern is a common cause of AutoSSL renewal failures. `--validate-nginx-acme` is the recommended command for diagnosing this class of failure.

#### N005 — Timeout/buffer values outside safe range

Flags http{} timeout and buffer directives outside operational bounds. Covers: `send_timeout`, `proxy_read_timeout`, `proxy_send_timeout`, `proxy_connect_timeout`, `keepalive_timeout`, `client_body_timeout`, `client_header_timeout`, `client_body_buffer_size`, `proxy_buffer_size`, `client_max_body_size`.

```
nginx.conf:2:1 ⚠️  N005 send timeout '3s' is below the minimum recommended value of 10s
nginx.conf:3:1 ⚠️  N005 proxy read timeout '600s' exceeds the maximum recommended value of 300s
```

#### N006 — send_timeout too short for upload size (HIGH)

Detects the dangerous combination of a short `send_timeout` or `proxy_read_timeout` (< 60s) alongside a large `client_max_body_size` (> 10m). Large file uploads will be silently killed mid-transfer.

```
myuser.conf:13:1 ❌ N006 send_timeout 3s is too short for client_max_body_size 200m — transfers larger than ~4 MB will time out silently
  💡 Raise send_timeout to at least 60s, or to match your largest expected transfer time (e.g. 300s for 200 MB on slow links)
```

**Real-world failure mode**: this config silently drops large media uploads in production. Fix: raise `send_timeout` to 300s.

#### N007 — ssl_stapling enabled but no OCSP URL (LOW)

Detects `ssl_stapling on;` on a certificate that lacks an OCSP responder URL (i.e. the cert's AIA extension has no `OCSP` entry). nginx will silently skip stapling — no error, no warning — and clients that expect OCSP stapling will fall back to their own OCSP lookup, adding latency.

```
myuser.conf:49:1 ℹ️  N007 ssl_stapling on, but 'domain.com.crt' has no OCSP responder URL
```

This typically affects self-signed or internal CA certificates. For production Let's Encrypt certs this rule rarely fires.

#### N008 — HTTPS site missing Strict-Transport-Security (HIGH)

Detects server blocks listening on port 443 that lack a `Strict-Transport-Security` (HSTS) header — either on the server block itself or in the global `http{}` block. Without HSTS, browsers never learn to pin the site to HTTPS, leaving the first HTTP request vulnerable to SSL stripping.

If HSTS is set globally in `nginx.conf http{}`, it covers all vhosts and no per-server findings are emitted.

```
myuser.conf:9:1 ❌ N008 'example.com' (line 9): HTTPS site missing Strict-Transport-Security header
```

Fix: `add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;`

Suppress per-server: `# reveal:allow-no-hsts`

#### N009 — server_tokens not disabled (MEDIUM)

Detects nginx configs where `server_tokens` is not set to `off`. By default nginx advertises its version in `Server` response headers and error pages (e.g. `Server: nginx/1.18.0`), giving attackers a free vulnerability shortlist. Fires once per file — it's a config gap, not a per-server issue.

```
myuser.conf:1:1 ⚠️  N009 server_tokens not disabled — nginx version exposed in Server header
```

Fix: add `server_tokens off;` to the `http{}` block in `nginx.conf`.

Suppress: `# reveal:allow-server-tokens`

#### N010 — Deprecated X-XSS-Protection header (LOW)

Detects `add_header X-XSS-Protection` in server blocks. This header was removed from the W3C spec and is ignored by Chrome (since 2019) and Firefox (since 2023). Its presence signals an outdated config and can introduce vulnerabilities in older IE/Edge versions. When the header comes from a shared snippet, the snippet path is surfaced so one edit fixes all affected sites.

```
myuser.conf:16:1 ℹ️  N010 Deprecated X-XSS-Protection header — remove and add Content-Security-Policy instead
```

Modern replacement: `Content-Security-Policy`. Suppress: `# reveal:allow-xss-protection`

#### N011 — SSL listener missing http2 (LOW)

Detects `listen 443 ssl` without `http2` on the same line. Certbot's `--nginx` plugin consistently strips `http2` when it rewrites listen directives, making this a repeat pattern after Let's Encrypt renewals. Note: nginx 1.25.1+ uses a separate `http2 on;` directive — this rule only fires on the inline form; a standalone `http2 on;` suppresses the finding.

```
myuser.conf:8:1 ℹ️  N011 'example.com' (line 8): SSL listener missing http2
```

Fix: change `listen 443 ssl;` → `listen 443 ssl http2;` (or add `http2 on;` for nginx ≥ 1.25.1).

Suppress per-server: `# reveal:allow-no-http2`

#### N012 — No rate limiting on server block (LOW/MEDIUM)

Two-level detection: **MEDIUM** if no `limit_req_zone` is defined anywhere in the file (rate limiting completely absent); **LOW** if a zone is defined but this server block uses no `limit_req` directive.

```
myuser.conf:8:1 ⚠️  N012 'example.com': no rate limiting configured (no limit_req_zone defined)
nginx.conf:7:1 ℹ️  N012 'example.com': limit_req_zone is configured but not applied to this server block
```

Suppress per-server: `# reveal:allow-no-rate-limit`

#### Filter file-rule findings by severity

`reveal check` already prints only violations. To focus on high and critical findings:

```bash
reveal check /etc/nginx/conf.d/users/myuser.conf --severity high
```

#### `--no-group`

By default, if one rule fires ≥ 10 times in a file, results collapse to a summary line. `--no-group` expands all occurrences:

```bash
reveal check /etc/nginx/conf.d/users/myuser.conf --no-group
```

---

### Operator Commands

These flags perform targeted inspections beyond static rule checking.

#### `--check-acl`

Checks that the `nobody` user has read+execute access to every `root` directive path (and each path component) in the config. The `nobody` user must be able to traverse into docroots for nginx ACME challenge serving to work.

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --check-acl
```

```
❌ ACL failures (1):
  /home/myuser/api/public   (api.example.com)  nobody cannot traverse /home/myuser/api (mode 700, no ACL entry)

✅ OK (2):
  /home/myuser/public_html  (example.com)
  /home/myuser/shop         (www.example.com)
```

There is one row per distinct root path, so two domains that share a root show only the first domain. Exit code 2 on any failure. Fix: `chmod o+x` each path component of the denied docroot.

Uses standard Unix `other` permission bits; falls back to `getfacl` ACL entries when standard permissions are insufficient.

#### `--extract acme-roots`

Finds all `/.well-known/acme-challenge` location blocks, resolves their root path (location-level or server-level fallback), and checks nobody ACL on each. One-command answer to "which domains can renew?"

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --extract acme-roots
```

```
  domain           acme root path            acl status
  -----------------------------------------------------
  example.com      /home/myuser/public_html  ✅ nobody:read OK
  www.example.com  /home/myuser/shop         ✅ nobody:read OK
  api.example.com  /home/myuser/api/public    ❌ DENIED  (nobody cannot traverse /home/myuser/api (mode 700, no ACL entry))
```

Exit code is 0 regardless of ACL status; use `--check-acl` or `--validate-nginx-acme` to gate.

#### `--check-conflicts`

Detects location block routing surprises:

- **prefix_overlap** — one non-regex location is a strict prefix of another (nginx longest-match wins, which may not be obvious)
- **regex_shadows_prefix** — a regex location pattern can match a prefix location's path

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --check-conflicts
```

```
⚠️  Conflicts (1):

  [example.com]
    /app.php  (line 17)
    ~ \.php$  (line 14)
    → regex location "~ \.php$" (line 14) may match requests also handled by prefix "/app.php" (line 17) — regex locations are evaluated after longest-prefix match; verify intended priority

ℹ️  Prefix overlaps (1):

  [example.com]
    /.well-known/  (line 11)
    /.well-known/acme-challenge/  (line 8)
    → "/.well-known/" (line 11) is a prefix of "/.well-known/acme-challenge/" (line 8) — nginx picks the longer match; requests to "/.well-known/" that don't match "/.well-known/acme-challenge" fall through to the shorter block
```

Exit code 2 on regex conflicts; info-only for prefix overlaps.

#### `--validate-nginx-acme`

The composed audit command. Chains extraction, ACL check, and live SSL cert check into a single per-domain table:

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme
```

```
  domain           acme root path            acl             ssl status
  ─────────────────────────────────────────────────────────────────────
  example.com      /home/myuser/public_html  ✅ ACL ok        ✅ 59d  (Dec 25, 2026)
  www.example.com  /home/myuser/shop         ✅ ACL ok        ✅ 59d  (Dec 25, 2026)
  api.example.com  /home/myuser/api/public   ❌ ACL DENIED    ❌ [Errno -2] Name or service not known
```

Exit code 2 on any ACL failure or failing live SSL check (expired, under 7 days, unreachable, hostname mismatch).

With `--only-failures` on 500+ domain configs, hide passing rows:

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme --only-failures
```

Prints `✅ No failures found.` when everything passes.

#### `--cpanel-certs`

Compares each SSL domain's on-disk cert (from `/var/cpanel/ssl/apache_tls/DOMAIN/combined`) against the live cert currently being served. Detects the "AutoSSL renewed but nginx hasn't reloaded" condition.

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --cpanel-certs
```

```
  domain           disk cert                     live cert                     match
  ──────────────────────────────────────────────────────────────────────────────────
  api.example.com  ⚫ not found                   ⚠️  error: [Errno -2] Name or service not known  ⚫ no disk cert
  example.com      ⚫ not found                   ✅ 59d  (Dec 25, 2026)         ⚫ no disk cert
  www.example.com  ⚫ not found                   ✅ 59d  (Dec 25, 2026)         ⚫ no disk cert
```

(Run on a host without `/var/cpanel/ssl`, so every disk cell is `⚫ not found`. On a cPanel server the disk cell reads like `✅ 87d  (May 25, 2026)` and the match cell compares serial numbers.)

Exit code 2 on stale or expired certs. `STALE` means the disk cert is newer than the live cert — nginx is serving a cert that AutoSSL has already renewed. Fix: `nginx -s reload`.

**Match detection**: uses SSL serial number comparison, not just expiry date — detects any cert replacement, not just expiry-based renewals.

#### `--diagnose`

Scans the nginx error log for ACME/SSL failure patterns, grouped by SSL domain with count and last-seen timestamp. Retroactively diagnoses incidents already in the log.

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --diagnose
```

```
nginx error log: /var/log/nginx/error.log
  domain            pattern                 count  last seen
  ──────────────────────────────────────────────────────────
  example.com       ⚠️  Not Found (ENOENT)      1  2026/10/26 09:11:00
  shop.example.com  ❌ Permission Denied         2  2026/10/26 14:05:01

Sample (most recent match per type):
  [example.com / not_found]
    2026/10/26 09:11:00 [error] 1234#0: *3 open() "/home/myuser/public_html/.well-known/acme-challenge/x" failed (2: No such
  [shop.example.com / permission_denied]
    2026/10/26 14:05:01 [error] 1234#0: *2 open() "/home/myuser/shop/.well-known/acme-challenge/def" failed (13: Permission
```

Timestamps keep nginx's `YYYY/MM/DD HH:MM:SS` form; SSL errors read `❌ SSL Error`.

**Detected patterns:**
- `permission_denied` — nginx can't read `/.well-known/acme-challenge/` (ACL failure)
- `ssl_error` — SSL certificate load/handshake error
- `not_found` — ACME challenge file not found (ACME root mismatch)

Auto-detects error log path from the config's `error_log` directive, or falls back to cPanel defaults. Override with `--log-path`:

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --diagnose --log-path /var/log/nginx/error.log
```

Exit code 2 on `permission_denied` or `ssl_error` hits; exit 0 on `not_found` only or clean log. Exits 1 when no error log can be found (`⚠️  No nginx error log found.`).

#### `--global-audit`

Audits the `http{}` block and main context of `nginx.conf` for missing security and operational directives. Complements `--audit` — `--audit` shows the fleet trend, `--global-audit` shows what the global config is actually missing.

```bash
reveal /etc/nginx/nginx.conf --global-audit
reveal /etc/nginx/nginx.conf --global-audit --only-failures
```

```
  directive                             severity  context  status
  ───────────────────────────────────────────────────────────────
  add_header Strict-Transport-Security  HIGH    http{}   ❌ missing
  add_header X-Content-Type-Options     MED     http{}   ❌ missing
  add_header X-Frame-Options            MED     http{}   ❌ missing
  server_tokens off                     MED     http{}   ✅ present
  ssl_protocols                         MED     http{}   ❌ missing
  client_max_body_size                  LOW     http{}   ❌ missing
  limit_req_zone                        LOW     http{}   ❌ missing
  resolver                              LOW     http{}   ❌ missing
  gzip on                               INFO    http{}   ❌ missing
  worker_processes                      INFO    main     ✅ present
```

Rows are sorted by severity. Exit code 2 when any check is missing, including INFO ones such as `gzip on`. Supports `--only-failures` and `--format json`.

---

### Domain Extraction Pipeline

```bash
# Extract all SSL domains as ssl:// URIs
reveal /etc/nginx/conf.d/users/myuser.conf --extract domains

# Check them all in one pass
reveal /etc/nginx/conf.d/users/myuser.conf --extract domains | reveal --stdin --check

# Show only expiring/failed
reveal /etc/nginx/conf.d/users/myuser.conf --extract domains | reveal --stdin --check --only-failures
```

---

### Operator Workflow: Diagnosing an SSL Renewal Failure

When a domain's cert stopped renewing and you don't know why:

```bash
# Step 1: Scope — how bad is it?
reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme --only-failures

# Step 2: Is nobody blocked from the docroot?
reveal cpanel://myuser/acl-check
# or per-config:
reveal /etc/nginx/conf.d/users/myuser.conf --check-acl

# Step 3: What has nginx been failing on?
reveal /etc/nginx/conf.d/users/myuser.conf --diagnose

# Step 4: Has AutoSSL already renewed but nginx hasn't loaded it?
reveal /etc/nginx/conf.d/users/myuser.conf --cpanel-certs

# Step 5: Are ACME paths consistent across all server blocks?
reveal /etc/nginx/conf.d/users/myuser.conf --extract acme-roots

# Step 6: Any location routing surprises?
reveal /etc/nginx/conf.d/users/myuser.conf --check-conflicts

# Step 7: Are there problematic timeout settings?
reveal check /etc/nginx/conf.d/users/myuser.conf
```

---

### Auto-Generated File Skip

Files containing `# reveal: generated`, `# Generated by ...`, `# @generated`, or `# This file is automatically generated` in the first 15 lines are silently skipped in recursive `--check` sweeps. Add `# reveal: generated` to cPanel-managed auto-generated configs to remove them from directory-wide reports.

---

### Flags Reference

| Flag | Description |
|------|-------------|
| `--check` | Deprecated flag — routes to `reveal check <path>`. Use `reveal check <path>` directly. |
| `--only-failures` | Suppress passing rows in `--check` and `--validate-nginx-acme` |
| `--no-group` | Disable result collapsing (default: ≥10 occurrences → summary) |
| `--server-name DOMAIN` | Filter output to server blocks with this `server_name` directive |
| `--check-acl` | Check nobody-user ACL access on all `root` paths |
| `--extract acme-roots` | ACME root path + nobody ACL status per domain |
| `--extract domains` | Output all SSL domains as `ssl://` URIs for piping |
| `--check-conflicts` | Detect prefix overlap and regex-shadows-prefix location issues |
| `--validate-nginx-acme` | Composed: ACME root + ACL + live SSL per domain |
| `--global-audit` | Audit nginx.conf http{} block for missing security/operational directives |
| `--cpanel-certs` | Compare disk cert vs live cert per SSL domain |
| `--diagnose` | Scan nginx error log for ACME/SSL failure patterns |
| `--log-path PATH` | Override error log path for `--diagnose` |
| `--audit` | Fleet consistency matrix across all enabled vhosts (`nginx://` only) |

**`reveal check` subcommand flags** (apply to `reveal check <path>`):

| Flag | Description |
|------|-------------|
| `--select RULES` | Run only these rules or categories (e.g., `N004` or `N,E`). Useful for focusing on one class of issue in large generated configs. |
| `--ignore RULES` | Skip these rules or categories (e.g., `--ignore N011,E501`). Suppress certbot-stripped http2 and line-length noise on cPanel configs. |
| `--severity LEVEL` | Minimum severity to report: `low`, `medium`, `high`, `critical` |
| `--no-group` | Disable rule collapsing (by default, ≥10 occurrences of one rule collapse to a summary) |

---

### Rules Reference

| Rule | Severity | Detects |
|------|----------|---------|
| N001 | HIGH | Duplicate upstream backends |
| N002 | CRITICAL | SSL server missing certificate directives |
| N003 | MEDIUM | Proxy location missing forwarding headers |
| N004 | HIGH | ACME challenge root path inconsistency across server blocks |
| N005 | MEDIUM | Timeout/buffer values outside safe operational ranges |
| N006 | HIGH | `send_timeout` too short relative to `client_max_body_size` (silent upload kills) |
| N007 | LOW | `ssl_stapling on` but certificate has no OCSP responder URL — stapling will silently fail |
| N008 | HIGH | HTTPS server block missing `Strict-Transport-Security` header |
| N009 | MEDIUM | `server_tokens` not disabled (nginx version exposed in response headers) |
| N010 | LOW | Deprecated `X-XSS-Protection` header present (removed from W3C spec, ignored by Chrome) |
| N011 | LOW | SSL listener missing `http2` (Certbot strips it on renewal) |
| N012 | LOW/MEDIUM | No `limit_req` applied to server block (escalates to MEDIUM if no zone defined) |

---

## See Also

- [CPANEL_ADAPTER_GUIDE.md](CPANEL_ADAPTER_GUIDE.md) — cPanel user environment inspection
- [SSL_ADAPTER_GUIDE.md](SSL_ADAPTER_GUIDE.md) — live SSL certificate analysis
- [DOMAIN_ADAPTER_GUIDE.md](DOMAIN_ADAPTER_GUIDE.md) — DNS + HTTP health checks
- `reveal help://nginx` — inline help and quick reference
- `reveal help://cpanel` — cpanel adapter inline help
- [RECIPES.md](../guides/RECIPES.md) — task-based workflows including nginx+cpanel patterns

```bash
reveal help://nginx     # inline help (file-based analysis)
reveal help://ssl       # SSL adapter
reveal help://domain    # domain adapter
```
