---
title: cPanel Adapter Guide
category: adapter-guide
adapter: cpanel://
---
# cPanel Adapter Guide (`cpanel://`)

**Stability**: 🟡 Beta
**Auth**: Must run as root (or with read access to `/var/cpanel/userdata/`)
**Network**: None — all operations are filesystem-based

---

## Overview

The `cpanel://` adapter provides a first-class view of a cPanel user's web environment. It reads the cPanel filesystem conventions (`/var/cpanel/userdata/`, `/var/cpanel/ssl/apache_tls/`) to surface domain inventory, SSL cert health, and docroot ACL status — without touching the WHM API.

```
cpanel://USERNAME[/element]
```

**Available elements:**

| Element | Description |
|---------|-------------|
| *(none)* | Overview: domain count, SSL summary, nginx config path |
| `domains` | All domains with docroots and type (addon/subdomain/main) |
| `ssl` | Disk cert health per domain from `/var/cpanel/ssl/apache_tls/` |
| `acl-check` | `nobody` ACL status on every domain docroot |

---

## Quick Start

```bash
# Overview: how many domains, cert health snapshot, nginx config path
reveal cpanel://myuser

# See all domains
reveal cpanel://myuser/domains

# Cert health (every SSL domain, sorted failures first)
reveal cpanel://myuser/ssl

# ACL check (is nobody user allowed into every docroot?)
reveal cpanel://myuser/acl-check
```

---

## Elements

### Overview (`cpanel://USERNAME`)

Shows at a glance: domain count, SSL status summary (count by ok/expiring/critical/expired/missing), and path to the nginx config.

```
cPanel user: myuser
  userdata dir: /var/cpanel/userdata/myuser ✅
  nginx config: /etc/nginx/conf.d/users/myuser.conf
  domains: 12

  SSL status:
    ✅ ok: 9
    ⚠️  expiring: 2
    ❌ critical: 1

  Next steps:
    reveal cpanel://myuser/domains    # All domains + docroots
    reveal cpanel://myuser/ssl        # Cert health per domain
    reveal cpanel://myuser/acl-check  # nobody ACL on docroots
    reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme  # Full ACME audit
```

---

### Domain Listing (`cpanel://USERNAME/domains`)

Lists every addon, subdomain, and parked domain with its document root and type.

```bash
reveal cpanel://myuser/domains
```

```
Domains for cPanel user: myuser  (12 total)

  domain                       type         docroot
  ────────────────────────────────────────────────────────────
  myuser.example.com           main_domain  /home/myuser/public_html
  shop.example.com             addon        /home/myuser/shop
  api.example.com              subdomain    /home/myuser/api/public
  staging.example.com          subdomain    /home/myuser/staging
  ...
```

Source: `/var/cpanel/userdata/USERNAME/` — one file per domain.

---

### SSL Disk Cert Health (`cpanel://USERNAME/ssl`)

Reads `/var/cpanel/ssl/apache_tls/DOMAIN/combined` for every domain and reports expiry status.

```bash
reveal cpanel://myuser/ssl
```

```
SSL disk certs for cPanel user: myuser
  source: /var/cpanel/ssl/apache_tls/DOMAIN/combined
  summary: 9 ok, 2 expiring, 1 critical

  domain                       status
  ─────────────────────────────────────────────────────────
  critical.example.com         ❌ 3d  (2026-03-02)
  expiring1.example.com        ⚠️  18d  (2026-03-17)
  expiring2.example.com        ⚠️  22d  (2026-03-21)
  myuser.example.com           ✅ 87d  (2026-05-25)
  shop.example.com             ✅ 87d  (2026-05-25)
  ...
  → reveal cpanel://myuser/acl-check  # Check docroot ACL
  → reveal /etc/nginx/conf.d/users/myuser.conf --cpanel-certs  # Compare disk vs live
```

Results are sorted: critical → expired → error → expiring → missing → ok.

**Status values:**

| Icon | Status | Meaning |
|------|--------|---------|
| ✅ | ok | Healthy, expires in > 30 days |
| ⚠️ | expiring | Expires in 8–30 days |
| ❌ | critical | Expires in ≤ 7 days |
| ❌ | expired | Already expired |
| ⚫ | missing | No cert file at expected path |
| ❌ | error | File exists but unreadable |

#### `--dns-verified` flag

On large multi-domain accounts, some "critical" or "expiring" domains may belong to former customers whose DNS has been pointed away — the disk cert is expiring but no users are affected.

```bash
reveal cpanel://myuser/ssl --dns-verified
```

With `--dns-verified`:
- Each domain gets a DNS lookup (`socket.getaddrinfo`)
- Domains that return NXDOMAIN are displayed with a `[nxdomain]` tag
- NXDOMAIN domains are **excluded from summary counts**
- The summary shows both the active count and the excluded count:

```
  summary: 1 critical  (2 nxdomain-excluded: 2 critical)
  dns-verified: NXDOMAIN domains shown but excluded from summary counts

  domain                       status
  ─────────────────────────────────────────────────────────────
  real-critical.example.com    ❌ 3d  (2026-03-02)
  gone1.example.com            ❌ 3d  (2026-03-02)  [nxdomain]
  gone2.example.com            ❌ 5d  (2026-03-04)  [nxdomain]
```

**Scope**: NXDOMAIN only. Domains that resolve but point to a different server are not excluded (that's a separate investigation — see `--cpanel-certs` for disk-vs-live comparison).

---

### ACL Check (`cpanel://USERNAME/acl-check`)

Verifies that the `nobody` user has read+execute access to the docroot of every domain. This is required for nginx to serve ACME challenge files during Let's Encrypt renewal.

```bash
reveal cpanel://myuser/acl-check
```

```
Docroot ACL check for cPanel user: myuser
  summary: 11 ok, 1 denied

  domain                       status          docroot
  ──────────────────────────────────────────────────────────────────────────
  myuser.example.com           ✅ ok           /home/myuser/public_html
  shop.example.com             ✅ ok           /home/myuser/shop
  api.example.com              ❌ denied       /home/myuser/api/public
  ...

❌ ACL failures detected — 'nobody' cannot read docroot(s).
   Fix: chmod o+x on each path component of the docroot.
```

The check tests each path component of the docroot using standard Unix `other` permission bits (falling back to `getfacl` when ACLs are in use).

**Fix when denied:**
```bash
# Grant nobody execute-traverse on each directory component
chmod o+x /home/myuser
chmod o+x /home/myuser/api
chmod o+x /home/myuser/api/public
```

---

## JSON Output

All elements support `--format=json` for scripting and pipeline use:

```bash
# Machine-readable cert health
reveal cpanel://myuser/ssl --format=json | jq '.certs[] | select(.status != "ok")'

# Domain list for scripting
reveal cpanel://myuser/domains --format=json | jq -r '.domains[].domain'

# ACL failures only
reveal cpanel://myuser/acl-check --format=json | jq '.domains[] | select(.acl_status == "denied")'

# Pipe SSL URI list for batch checking
reveal cpanel://myuser/domains --format=json \
  | jq -r '.domains[].domain | "ssl://" + .' \
  | reveal --stdin --check --only-failures
```

---

## Operator Workflows

### Full SSL Health Check

The standard sequence for diagnosing SSL or ACME renewal issues on a cPanel account:

```bash
# 1. Overview — get the lay of the land
reveal cpanel://myuser

# 2. ACL check — is nobody allowed in? (most common renewal blocker)
reveal cpanel://myuser/acl-check

# 3. Disk cert health — what's expiring?
reveal cpanel://myuser/ssl

# 4. Disk vs live cert comparison — has nginx loaded the renewed cert?
reveal /etc/nginx/conf.d/users/myuser.conf --cpanel-certs

# 5. Full composed audit — ACME paths + ACL + live cert in one table
reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme

# 6. Error log audit — what has nginx actually been failing on?
reveal /etc/nginx/conf.d/users/myuser.conf --diagnose
```

### Large Account: Noise Reduction

For accounts with 100+ domains including inactive/former-customer domains:

```bash
# Filter DNS-dead domains from the cert summary
reveal cpanel://myuser/ssl --dns-verified

# Show only nginx ACME failures
reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme --only-failures

# Show only ACL failures
reveal cpanel://myuser/acl-check --format=json | jq '.domains[] | select(.acl_status == "denied")'
```

### Automated Monitoring

```bash
#!/bin/bash
# Daily cPanel SSL health check — exit non-zero if critical issues found
reveal cpanel://myuser/ssl --format=json | python3 -c "
import json, sys
data = json.load(sys.stdin)
s = data['summary']
critical = s.get('critical', 0) + s.get('expired', 0)
if critical:
    print(f'ALERT: {critical} critical/expired certs for myuser')
    sys.exit(2)
"
```

---

## Composing with nginx Commands

The `cpanel://` adapter and the nginx file analyzer are designed to be used together. The cpanel adapter works from cPanel's filesystem; the nginx commands work from nginx's config.

```bash
# cPanel ACL check is filesystem-authoritative:
reveal cpanel://myuser/acl-check

# nginx ACME audit verifies config routing AND ACL:
reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme
# ↑ Use both: they catch different failure modes
```

**Why they differ**: `cpanel://acl-check` checks the `nobody` user's filesystem permissions on docroots as cPanel defines them. `--validate-nginx-acme` reads the *nginx config* to find the actual path nginx will serve ACME challenges from, then checks ACL on that path — which may differ from cPanel's `documentroot` if the nginx config has a custom `root` directive in the ACME location block.

See [NGINX_ANALYZER_GUIDE.md](NGINX_ANALYZER_GUIDE.md) for all nginx operator commands.

---

## Filesystem Paths Used

| Path | Purpose |
|------|---------|
| `/var/cpanel/userdata/USERNAME/` | Domain inventory (one file per domain) |
| `/var/cpanel/ssl/apache_tls/DOMAIN/combined` | On-disk SSL cert (PEM, leaf + chain) |
| `/etc/nginx/conf.d/users/USERNAME.conf` | nginx user config (detected automatically) |

---

## Flags Reference

| Flag | Element | Description |
|------|---------|-------------|
| `--dns-verified` | `ssl` | Exclude NXDOMAIN domains from summary counts |
| `--format=json` | all | JSON output for scripting |

---

## See Also

- `reveal help://cpanel` — inline help with live examples
- [NGINX_ANALYZER_GUIDE.md](NGINX_ANALYZER_GUIDE.md) — all nginx operator flags
- [SSL_ADAPTER_GUIDE.md](SSL_ADAPTER_GUIDE.md) — live SSL certificate inspection
- `reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme` — full audit
- `reveal /etc/nginx/conf.d/users/USERNAME.conf --cpanel-certs` — disk vs live comparison
