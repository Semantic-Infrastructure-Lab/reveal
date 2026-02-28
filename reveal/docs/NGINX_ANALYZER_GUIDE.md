---
title: nginx Analyzer Guide
category: analyzer-guide
analyzer: nginx config files
---
# nginx Analyzer Guide

**Input**: nginx config files (`.conf`, `nginx.conf`)
**URI**: plain file paths — `reveal /path/to/nginx.conf`
**Stability**: 🟢 Stable (structure display, `--check`) / 🟡 Beta (operator commands)

---

## Overview

The nginx analyzer reads nginx configuration files and surfaces structure, rules, and operator-focused diagnostic commands. Unlike URI-scheme adapters, nginx is invoked with a plain file path:

```bash
reveal /etc/nginx/nginx.conf
reveal /etc/nginx/conf.d/users/myuser.conf
```

The analyzer covers two modes:
- **Structure display** — show servers, locations, upstreams, directives
- **Operator commands** — `--check`, `--check-acl`, `--validate-nginx-acme`, `--cpanel-certs`, `--diagnose`, and more

---

## Quick Start

```bash
# Show config structure
reveal /etc/nginx/conf.d/users/myuser.conf

# Run all nginx rules (N001–N006)
reveal /etc/nginx/conf.d/users/myuser.conf --check

# Full ACME+ACL+SSL audit (the single command that catches most SSL renewal failures)
reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme

# Focus on one domain in a large multi-domain config
reveal /etc/nginx/conf.d/users/myuser.conf --domain example.com
```

---

## Structure Display

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

### `--domain` filter

Large cPanel user configs have one server block per domain — a 1,500-line file for 30 domains. `--domain` filters output to just the matching server block(s):

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --domain shop.example.com
```

Matches on `server_name` and all aliases. Essential for targeting a specific domain.

---

## Rule Checking (`--check`)

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --check
```

Runs the N001–N006 nginx rules against the config. Results are grouped when a rule fires many times in one file (configurable with `--no-group`).

### N001 — Duplicate backends

Detects multiple `upstream` blocks pointing to the same `server:port`. A common copy-paste misconfiguration that can cause confusing traffic distribution.

```
N001  HIGH  Upstream app2 (line 45) duplicates backend of app1 (127.0.0.1:8000)
```

### N002 — SSL server missing certificate

Detects `listen 443 ssl` without `ssl_certificate` and `ssl_certificate_key`. The server will fail to start.

```
N002  HIGH  Server block at line 12 listens on SSL (443) but lacks ssl_certificate directives
```

### N003 — Proxy location missing headers

Detects `proxy_pass` locations missing recommended headers (`X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`, `Host`). Without these, the upstream sees the nginx IP, not the real client IP.

```
N003  MEDIUM  proxy_pass at line 34: missing X-Real-IP, X-Forwarded-For headers
```

### N004 — ACME challenge path inconsistency

Detects server blocks with different `root` paths for `/.well-known/acme-challenge/` locations. Let's Encrypt uses one certbot/webroot directory — if some server blocks point elsewhere, renewal fails for those domains silently.

```
N004  MEDIUM  ACME challenge root '/home/olduser/public_html' differs from common path '/home/myuser/public_html'
```

**Context**: This is the direct cause of the Feb 2026 Sociamonials SSL incident. `--validate-nginx-acme` is the recommended command for diagnosing this class of failure.

### N005 — Timeout/buffer values outside safe range

Flags http{} timeout and buffer directives outside operational bounds. Covers: `send_timeout`, `proxy_read_timeout`, `proxy_send_timeout`, `proxy_connect_timeout`, `keepalive_timeout`, `client_body_timeout`, `client_header_timeout`, `client_body_buffer_size`, `proxy_buffer_size`, `client_max_body_size`.

```
N005  MEDIUM  send_timeout 3s is below minimum of 10s (may cause silent connection drops)
N005  MEDIUM  proxy_read_timeout 600s exceeds maximum of 300s (resource exhaustion risk)
```

### N006 — send_timeout too short for upload size (HIGH)

Detects the dangerous combination of a short `send_timeout` or `proxy_read_timeout` (< 60s) alongside a large `client_max_body_size` (> 10m). Large file uploads will be silently killed mid-transfer.

```
N006  HIGH  send_timeout 30s with client_max_body_size 200m: uploads over ~110MB will time out silently
            Minimum send_timeout for 200m at typical speeds: ~300s
```

**Real-world incident**: Exact config that caused silent media upload failures on Sociamonials (Feb 2026). Fix: raise `send_timeout` to 300s.

### `--only-failures` with `--check`

On configs with many domains, suppress passing rules — see only actionable findings:

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --check --only-failures
```

### `--no-group`

By default, if one rule fires ≥ 10 times in a file, results collapse to a summary line. `--no-group` expands all occurrences:

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --check --no-group
```

---

## Operator Commands

These flags perform targeted inspections beyond static rule checking.

### `--check-acl`

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

### `--extract acme-roots`

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

### `--check-conflicts`

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

### `--validate-nginx-acme`

The composed audit command. Chains extraction, ACL check, and live SSL cert check into a single per-domain table:

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme
```

```
ACME+ACL+SSL audit: /etc/nginx/conf.d/users/myuser.conf

  domain                acme root                  acl    ssl cert
  ──────────────────────────────────────────────────────────────────────────
  example.com           /home/myuser/public_html   ✅ ok  ✅ 87d
  shop.example.com      /home/myuser/shop          ✅ ok  ✅ 87d
  api.example.com       /home/myuser/api/public    ❌ denied  ⚠️  18d
  old.example.com       /home/myuser/public_html   ✅ ok  ❌ EXPIRED

Exit: 2 (failures found)
```

Exit code 2 on any ACL failure or SSL expiry/critical status.

#### With `--only-failures`

On 500+ domain configs, hide passing rows:

```bash
reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme --only-failures
```

Prints `✅ No failures found.` when everything passes.

### `--cpanel-certs`

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

### `--diagnose`

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

---

## Domain Extraction Pipeline

```bash
# Extract all SSL domains as ssl:// URIs
reveal /etc/nginx/conf.d/users/myuser.conf --extract domains

# Check them all in one pass
reveal /etc/nginx/conf.d/users/myuser.conf --extract domains | reveal --stdin --check

# Show only expiring/failed
reveal /etc/nginx/conf.d/users/myuser.conf --extract domains | reveal --stdin --check --only-failures
```

---

## Operator Workflow: Diagnosing an SSL Renewal Failure

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

## Auto-Generated File Skip

Files containing `# reveal: generated`, `# Generated by ...`, `# @generated`, or `# This file is automatically generated` in the first 15 lines are silently skipped in recursive `--check` sweeps. Add `# reveal: generated` to cPanel-managed auto-generated configs to remove them from directory-wide reports.

---

## Flags Reference

| Flag | Description |
|------|-------------|
| `--check` | Run N001–N006 rules; exit 2 on HIGH findings |
| `--only-failures` | Suppress passing rows in `--check` and `--validate-nginx-acme` |
| `--no-group` | Disable result collapsing (default: ≥10 occurrences → summary) |
| `--domain DOMAIN` | Filter output to server blocks matching DOMAIN |
| `--check-acl` | Check nobody-user ACL access on all `root` paths |
| `--extract acme-roots` | ACME root path + nobody ACL status per domain |
| `--extract domains` | Output all SSL domains as `ssl://` URIs for piping |
| `--check-conflicts` | Detect prefix overlap and regex-shadows-prefix location issues |
| `--validate-nginx-acme` | Composed: ACME root + ACL + live SSL per domain |
| `--only-failures` | (with `--validate-nginx-acme`) suppress passing rows |
| `--cpanel-certs` | Compare disk cert vs live cert per SSL domain |
| `--diagnose` | Scan nginx error log for ACME/SSL failure patterns |
| `--log-path PATH` | Override error log path for `--diagnose` |

---

## Rules Reference

| Rule | Severity | Detects |
|------|----------|---------|
| N001 | HIGH | Duplicate upstream backends |
| N002 | HIGH | SSL server missing certificate directives |
| N003 | MEDIUM | Proxy location missing forwarding headers |
| N004 | MEDIUM | ACME challenge root path inconsistency across server blocks |
| N005 | MEDIUM | Timeout/buffer values outside safe operational ranges |
| N006 | HIGH | `send_timeout` too short relative to `client_max_body_size` (silent upload kills) |

---

## See Also

- [CPANEL_ADAPTER_GUIDE.md](CPANEL_ADAPTER_GUIDE.md) — cPanel user environment inspection
- [SSL_ADAPTER_GUIDE.md](SSL_ADAPTER_GUIDE.md) — live SSL certificate analysis
- `reveal help://nginx` — inline help and quick reference
- `reveal help://cpanel` — cpanel adapter inline help
- [RECIPES.md](RECIPES.md) — task-based workflows including nginx+cpanel patterns
