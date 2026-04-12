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

**Searches**: `/etc/nginx/sites-enabled/` (extension-less files) and `/etc/nginx/conf.d/` (`*.conf` files). Both symlinks and regular files are handled.

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

### Example Output

#### `reveal nginx://smd-ops.mytia.net`

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

#### `reveal nginx://`

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

### Workflows

#### After nginx config change

```bash
reveal nginx://smd-ops.mytia.net            # verify config was applied
reveal nginx://smd-ops.mytia.net/ports      # check SSL block is present
reveal nginx://smd-ops.mytia.net/upstream   # verify upstream still reachable
reveal ssl://smd-ops.mytia.net --check      # verify SSL cert intact
```

#### Diagnose unexpected redirect

```bash
reveal nginx://smd-ops.mytia.net            # see all location blocks at once
reveal nginx://smd-ops.mytia.net/locations  # inspect location targets
reveal domain://smd-ops.mytia.net --check   # verify DNS + HTTP response
```

#### Auth audit

```bash
reveal nginx://smd-ops.mytia.net/auth       # check auth_basic on/off
reveal nginx://smd-ops.mytia.net/config     # view raw config to verify
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
- **Remote servers**: nginx:// only works locally. For SSH-accessed nginx, use file-path form: `reveal /etc/nginx/conf.d/file.conf --check`
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
  server_tokens off             ❌       14       32  Move to nginx.conf http{} ↑
  X-Content-Type-Options        ❌       38        8  Move to nginx.conf http{} ↑
  X-Frame-Options               ❌       38        8  Move to nginx.conf http{} ↑
  http2 on 443 listener         ❌       21       25  Add per-site (certbot strips http2 on renewal)
  limit_req applied             ❌        1       45  Add zones to nginx.conf, then limit_req per sensitive location
  X-XSS-Protection (depr.)     —        38        —  Remove — deprecated since 2019, ignored by Chrome

  ↑ Consolidation: server_tokens off, X-Content-Type-Options, X-Frame-Options
    Move these to nginx.conf http{} — one change fixes all sites.

  Snippet Consistency:
    snippets/tia-security-headers.conf  — included by 38, missing from 8
       Missing from: belize.mytia.net, motion.mytia.net, ...

Exit code: 2 (gaps found)
```

**Consolidation hint**: when a directive appears in ≥50% of site configs but is absent from nginx.conf http{}, it's marked with `↑` as a consolidation opportunity — one line in nginx.conf fixes the whole fleet.

**`X-XSS-Protection`** is a deprecated header check — "Sites With" means sites that *have* the deprecated header (should remove it). "Sites Without" is `—` because absence is the correct state.

---

### JSON Output

```bash
reveal nginx://example.com --format=json
```

Returns a structured object with `config_file`, `symlink`, `ports`, `upstream`, `auth`, `locations` keys — suitable for scripting.

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
reveal /etc/nginx/conf.d/users/myuser.conf --domain example.com
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

#### `--domain` filter

Large cPanel user configs have one server block per domain — a 1,500-line file for 30 domains. `--domain` filters output to just the matching server block(s):

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --domain shop.example.com
```

Matches on `server_name` and all aliases. Essential for targeting a specific domain.

---

### Rule Checking (`--check`)

```bash
reveal check /etc/nginx/conf.d/users/myuser.conf

# Focus on ACME path issues only (useful on cPanel auto-generated configs)
reveal check /etc/nginx/conf.d/users/myuser.conf --select N004

# Suppress certbot-stripped http2 (N011) and line-length (E501) noise
reveal check /etc/nginx/conf.d/users/myuser.conf --ignore N011,E501
```

Runs the N001–N012 nginx rules against the config. Results are grouped when a rule fires many times in one file (configurable with `--no-group`).

#### N001 — Duplicate backends

Detects multiple `upstream` blocks pointing to the same `server:port`. A common copy-paste misconfiguration that can cause confusing traffic distribution.

```
N001  HIGH  Upstream app2 (line 45) duplicates backend of app1 (127.0.0.1:8000)
```

#### N002 — SSL server missing certificate

Detects `listen 443 ssl` without `ssl_certificate` and `ssl_certificate_key`. The server will fail to start.

```
N002  HIGH  Server block at line 12 listens on SSL (443) but lacks ssl_certificate directives
```

#### N003 — Proxy location missing headers

Detects `proxy_pass` locations missing recommended headers (`X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, `Host`). Without these, the upstream sees the nginx IP, not the real client IP.

```
N003  MEDIUM  proxy_pass at line 34: missing X-Real-IP, X-Forwarded-For headers
```

#### N004 — ACME challenge path inconsistency

Detects server blocks with different `root` paths for `/.well-known/acme-challenge/` locations. Let's Encrypt uses one certbot/webroot directory — if some server blocks point elsewhere, renewal fails for those domains silently.

```
N004  MEDIUM  ACME challenge root '/home/olduser/public_html' differs from common path '/home/myuser/public_html'
```

**Context**: This pattern was the direct cause of a Feb 2026 production SSL incident. `--validate-nginx-acme` is the recommended command for diagnosing this class of failure.

#### N005 — Timeout/buffer values outside safe range

Flags http{} timeout and buffer directives outside operational bounds. Covers: `send_timeout`, `proxy_read_timeout`, `proxy_send_timeout`, `proxy_connect_timeout`, `keepalive_timeout`, `client_body_timeout`, `client_header_timeout`, `client_body_buffer_size`, `proxy_buffer_size`, `client_max_body_size`.

```
N005  MEDIUM  send_timeout 3s is below minimum of 10s (may cause silent connection drops)
N005  MEDIUM  proxy_read_timeout 600s exceeds maximum of 300s (resource exhaustion risk)
```

#### N006 — send_timeout too short for upload size (HIGH)

Detects the dangerous combination of a short `send_timeout` or `proxy_read_timeout` (< 60s) alongside a large `client_max_body_size` (> 10m). Large file uploads will be silently killed mid-transfer.

```
N006  HIGH  send_timeout 30s with client_max_body_size 200m: uploads over ~110MB will time out silently
            Minimum send_timeout for 200m at typical speeds: ~300s
```

**Real-world incident**: Exact config that caused silent media upload failures in production (Feb 2026). Fix: raise `send_timeout` to 300s.

#### N007 — ssl_stapling enabled but no OCSP URL

Detects `ssl_stapling on;` on a certificate that lacks an OCSP responder URL (i.e. the cert's AIA extension has no `OCSP` entry). nginx will silently skip stapling — no error, no warning — and clients that expect OCSP stapling will fall back to their own OCSP lookup, adding latency.

```
N007  INFO  ssl_stapling on but /etc/nginx/ssl/domain.com.crt has no OCSP responder URL — stapling ineffective
```

This typically affects self-signed or internal CA certificates. For production Let's Encrypt certs this rule rarely fires.

#### N008 — HTTPS site missing Strict-Transport-Security (HIGH)

Detects server blocks listening on port 443 that lack a `Strict-Transport-Security` (HSTS) header — either on the server block itself or in the global `http{}` block. Without HSTS, browsers never learn to pin the site to HTTPS, leaving the first HTTP request vulnerable to SSL stripping.

If HSTS is set globally in `nginx.conf http{}`, it covers all vhosts and no per-server findings are emitted.

```
N008  HIGH  Server block 'example.com' missing Strict-Transport-Security header
```

Fix: `add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;`

Suppress per-server: `# reveal:allow-no-hsts`

#### N009 — server_tokens not disabled (MEDIUM)

Detects nginx configs where `server_tokens` is not set to `off`. By default nginx advertises its version in `Server` response headers and error pages (e.g. `Server: nginx/1.18.0`), giving attackers a free vulnerability shortlist. Fires once per file — it's a config gap, not a per-server issue.

```
N009  MEDIUM  server_tokens not disabled — nginx version exposed in response headers
```

Fix: add `server_tokens off;` to the `http{}` block in `nginx.conf`.

Suppress: `# reveal:allow-server-tokens`

#### N010 — Deprecated X-XSS-Protection header (LOW)

Detects `add_header X-XSS-Protection` in server blocks. This header was removed from the W3C spec and is ignored by Chrome (since 2019) and Firefox (since 2023). Its presence signals an outdated config and can introduce vulnerabilities in older IE/Edge versions. When the header comes from a shared snippet, the snippet path is surfaced so one edit fixes all affected sites.

```
N010  LOW  Deprecated X-XSS-Protection header in server block at line 45
```

Modern replacement: `Content-Security-Policy`. Suppress: `# reveal:allow-xss-protection`

#### N011 — SSL listener missing http2 (LOW)

Detects `listen 443 ssl` without `http2` on the same line. Certbot's `--nginx` plugin consistently strips `http2` when it rewrites listen directives, making this a repeat pattern after Let's Encrypt renewals. Note: nginx 1.25.1+ uses a separate `http2 on;` directive — this rule only fires on the inline form; a standalone `http2 on;` suppresses the finding.

```
N011  LOW  listen 443 ssl at line 12 missing http2 — HTTP/2 disabled for this site
```

Fix: change `listen 443 ssl;` → `listen 443 ssl http2;` (or add `http2 on;` for nginx ≥ 1.25.1).

Suppress per-server: `# reveal:allow-no-http2`

#### N012 — No rate limiting on server block (LOW/MEDIUM)

Two-level detection: **MEDIUM** if no `limit_req_zone` is defined anywhere in the file (rate limiting completely absent); **LOW** if a zone is defined but this server block uses no `limit_req` directive.

```
N012  MEDIUM  No limit_req_zone defined — server block has no rate limiting at all
N012  LOW     limit_req_zone defined but not applied to this server block (line 8)
```

Suppress per-server: `# reveal:allow-no-rate-limit`

#### `--only-failures` with `--check`

On configs with many domains, suppress passing rules — see only actionable findings:

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --check --only-failures
```

#### `--no-group`

By default, if one rule fires ≥ 10 times in a file, results collapse to a summary line. `--no-group` expands all occurrences:

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --check --no-group
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
ACL check: /etc/nginx/conf.d/users/myuser.conf

  domain               root                              status
  ──────────────────────────────────────────────────────────────
  example.com          /home/myuser/public_html          ✅ ok
  shop.example.com     /home/myuser/shop                 ✅ ok
  api.example.com      /home/myuser/api/public           ❌ denied
```

Exit code 2 on any failure. Fix: `chmod o+x` each path component of the denied docroot.

Uses standard Unix `other` permission bits; falls back to `getfacl` ACL entries when standard permissions are insufficient.

#### `--extract acme-roots`

Finds all `/.well-known/acme-challenge` location blocks, resolves their root path (location-level or server-level fallback), and checks nobody ACL on each. One-command answer to "which domains can renew?"

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --extract acme-roots
```

```
ACME challenge roots: /etc/nginx/conf.d/users/myuser.conf

  domain                root                              acl
  ────────────────────────────────────────────────────────────
  example.com           /home/myuser/public_html          ✅ ok
  shop.example.com      /home/myuser/shop                 ✅ ok
  api.example.com       /home/myuser/api/public           ❌ denied
```

#### `--check-conflicts`

Detects location block routing surprises:

- **prefix_overlap** — one non-regex location is a strict prefix of another (nginx longest-match wins, which may not be obvious)
- **regex_shadows_prefix** — a regex location pattern can match a prefix location's path

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --check-conflicts
```

```
Location conflicts: /etc/nginx/conf.d/users/myuser.conf

  server: example.com (line 12)
  ⚠️  prefix_overlap:
      location /.well-known/acme-challenge/ (line 15, 31 chars)
      location /.well-known/ (line 22, 15 chars)
      explanation: /.well-known/ is a prefix of /.well-known/acme-challenge/
                   nginx longest-prefix-wins applies
```

Exit code 2 on regex conflicts; info-only for prefix overlaps.

#### `--validate-nginx-acme`

The composed audit command. Chains extraction, ACL check, and live SSL cert check into a single per-domain table:

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme
```

```
ACME+ACL+SSL audit: /etc/nginx/conf.d/users/myuser.conf

  domain                acme root                  acl    ssl cert
  ──────────────────────────────────────────────────────────────────────
  example.com           /home/myuser/public_html   ✅ ok  ✅ 87d
  shop.example.com      /home/myuser/shop          ✅ ok  ✅ 87d
  api.example.com       /home/myuser/api/public    ❌ denied  ⚠️  18d
  old.example.com       /home/myuser/public_html   ✅ ok  ❌ EXPIRED

Exit: 2 (failures found)
```

Exit code 2 on any ACL failure or SSL expiry/critical status.

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
Disk vs live cert comparison: /etc/nginx/conf.d/users/myuser.conf

  domain                disk expiry     live expiry     match
  ─────────────────────────────────────────────────────────────────
  example.com           2026-05-25      2026-05-25      ✅ match
  shop.example.com      2026-06-01      2026-03-15      ⚠️  STALE (reload nginx)
  api.example.com       2026-05-28      2026-05-28      ✅ match
```

Exit code 2 on stale or expired certs. `STALE` means the disk cert is newer than the live cert — nginx is serving a cert that AutoSSL has already renewed. Fix: `nginx -s reload`.

**Match detection**: uses SSL serial number comparison, not just expiry date — detects any cert replacement, not just expiry-based renewals.

#### `--diagnose`

Scans the nginx error log for ACME/SSL failure patterns, grouped by SSL domain with count and last-seen timestamp. Retroactively diagnoses incidents already in the log.

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --diagnose
```

```
nginx error log audit: /etc/nginx/conf.d/users/myuser.conf
  log: /var/log/nginx/error.log (last 5000 lines)

  domain                pattern                count  last seen
  ─────────────────────────────────────────────────────────────────────
  api.example.com       permission_denied        47   2026-02-27 14:03
  shop.example.com      ssl_error                 3   2026-02-27 09:11

Exit: 2 (permission_denied or ssl_error hits found)
```

**Detected patterns:**
- `permission_denied` — nginx can't read `/.well-known/acme-challenge/` (ACL failure)
- `ssl_error` — SSL certificate load/handshake error
- `not_found` — ACME challenge file not found (ACME root mismatch)

Auto-detects error log path from the config's `error_log` directive, or falls back to cPanel defaults. Override with `--log-path`:

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --diagnose --log-path /var/log/nginx/error.log
```

Exit code 2 on `permission_denied` or `ssl_error` hits; exit 0 on `not_found` only or clean log.

#### `--global-audit`

Audits the `http{}` block and main context of `nginx.conf` for missing security and operational directives. Complements `--audit` — `--audit` shows the fleet trend, `--global-audit` shows what the global config is actually missing.

```bash
reveal /etc/nginx/nginx.conf --global-audit
reveal /etc/nginx/nginx.conf --global-audit --only-failures
```

```
Global http{} Audit: /etc/nginx/nginx.conf

  directive                      severity  context  status
  ─────────────────────────────────────────────────────────────────────
  gzip on                        INFO      http{}   ✅ present
  server_tokens off              MEDIUM    http{}   ❌ missing
  add_header Strict-Transport-Security  HIGH  http{}  ❌ missing
  add_header X-Content-Type-Options     MEDIUM  http{}  ❌ missing
  add_header X-Frame-Options            MEDIUM  http{}  ❌ missing
  ssl_protocols                  MEDIUM    http{}   ❌ missing
  resolver                       LOW       http{}   ❌ missing
  limit_req_zone                 LOW       http{}   ❌ missing
  client_max_body_size           LOW       http{}   ❌ missing
  worker_processes               INFO      main     ✅ present
```

Exit code 2 when any directives are missing. Supports `--only-failures` and `--format json`.

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
reveal /etc/nginx/conf.d/users/myuser.conf --check
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
| `--domain DOMAIN` | Filter output to server blocks matching DOMAIN |
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
| N002 | HIGH | SSL server missing certificate directives |
| N003 | MEDIUM | Proxy location missing forwarding headers |
| N004 | MEDIUM | ACME challenge root path inconsistency across server blocks |
| N005 | MEDIUM | Timeout/buffer values outside safe operational ranges |
| N006 | HIGH | `send_timeout` too short relative to `client_max_body_size` (silent upload kills) |
| N007 | INFO | `ssl_stapling on` but certificate has no OCSP responder URL — stapling will silently fail |
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
