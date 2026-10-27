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
| `full-audit` | Composite: `ssl` + `acl-check` + nginx ACME check in one pass; exits 2 on any failure — the preferred single command for agents |

`reveal cpanel://help/api` (no username) prints a WHM & cPanel API quick reference: common commands, filesystem paths and domain types.

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

# Composite: ssl + acl-check + nginx ACME in one pass (exits 2 on failure)
reveal cpanel://myuser/full-audit
```

---

## Elements

### Overview (`cpanel://USERNAME`)

Shows at a glance: domain count, SSL status summary (count by ok/expiring/critical/expired/missing), and path to the nginx config.

```
cPanel user: myuser
  userdata dir: /var/cpanel/userdata/myuser ✅
  nginx config: /etc/nginx/conf.d/users/myuser.conf
  domains: 9

  SSL status:
    ✅ ok: 2
    ⚠️  expiring: 1
    ❌ critical: 3
    ❌ expired: 1
    ⚫ missing: 1
    ❌ error: 1

  Next steps:
    reveal cpanel://myuser/full-audit  # SSL + ACL + nginx in one pass
    reveal cpanel://myuser/domains     # All domains + docroots
    reveal cpanel://myuser/ssl         # Cert health per domain
    reveal cpanel://myuser/acl-check   # nobody ACL on docroots
    reveal /etc/nginx/conf.d/users/myuser.conf --validate-nginx-acme  # nginx ACME audit only
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
  summary: 1 expired (1 subdomain/parked), 3 critical, 1 error, 1 expiring, 1 missing, 2 ok

  domain                status
  ────────────────────────────────────────────────────────────
  expired.example.com   ❌ EXPIRED 5d ago  (2026-10-23)
  critical.example.com  ⚠️  3d  (2026-10-31)
  gone1.invalid         ⚠️  3d  (2026-10-31)
  gone2.invalid         ⚠️  5d  (2026-11-02)
  broken.example.com    ❌ Failed to parse certificate file …
  expiring.example.com  ⚠️  18d  (2026-11-15)
  nocert.example.com    ⚫ no cert at /var/cpanel/ssl/apache_tls/nocert.example.com/combined
  example.com           ✅ 87d  (2027-01-23)
  shop.example.com      ✅ 87d  (2027-01-23)

  → reveal cpanel://myuser/acl-check  # Check docroot ACL
  → reveal cpanel://myuser/ssl --check-live  # Cross-reference disk vs live cert
```

Results are sorted: expired → critical → error → expiring → missing → ok. The summary notes how many expired certs belong to subdomains or parked domains.

**Status values:**

| Icon | Status | Meaning |
|------|--------|---------|
| ✅ | ok | Healthy, expires in 30 days or more |
| ⚠️ | expiring | Expires in 7–29 days |
| ⚠️ | critical | Expires in under 7 days (`❌` in the overview's SSL status block) |
| ❌ | expired | Already expired: `❌ EXPIRED Nd ago` |
| ⚫ | missing | No cert file at expected path |
| ❌ | error | File exists but unreadable |

#### `--dns-verified` flag

On large multi-domain accounts, some "critical" or "expiring" domains may belong to former customers whose DNS has been pointed away — the disk cert is expiring but no users are affected.

```bash
reveal cpanel://myuser/ssl --dns-verified
```

With `--dns-verified`, each domain is resolved (`socket.getaddrinfo`): NXDOMAIN domains are tagged `[nxdomain]` and domains that resolve to an IP not on this server are tagged `[→ elsewhere]`. Both are shown but **excluded from the summary counts**, which list each excluded group separately:

```
  summary: none  (8 nxdomain-excluded: 1 expired, 3 critical, 1 error, 1 expiring, 1 missing, 1 ok)  (1 elsewhere-excluded: 1 ok)
  dns-verified: NXDOMAIN and elsewhere-resolving domains excluded from summary counts

  domain                status
  ────────────────────────────────────────────────────────────
  expired.example.com   ❌ EXPIRED 5d ago  (2026-10-23)  [nxdomain]
  critical.example.com  ⚠️  3d  (2026-10-31)  [nxdomain]
  ...
  example.com           ✅ 87d  (2027-01-23)  [→ elsewhere]
  shop.example.com      ✅ 87d  (2027-01-23)  [nxdomain]
```

In JSON, `dns_resolves: false` marks NXDOMAIN and `dns_points_here: false` marks a domain served elsewhere.

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

  → reveal cpanel://myuser/ssl  # Check cert status
  → reveal /etc/nginx/conf.d/users/myuser.conf --check-acl  # Full nginx ACL check
```

`acl-check` exits 0 even when a docroot is denied; use `full-audit` (exit 2) or `jq '.has_failures'` to gate.

The check tests each path component of the docroot using standard Unix `other` permission bits (falling back to `getfacl` when ACLs are in use).

**Fix when denied:**
```bash
# Grant nobody execute-traverse on each directory component
chmod o+x /home/myuser
chmod o+x /home/myuser/api
chmod o+x /home/myuser/api/public
```

---

### Full Audit (`cpanel://USERNAME/full-audit`)

Composite check combining `ssl`, `acl-check`, and the nginx ACME path check in a single pass. Exits with code 2 if any check fails — designed as the one-shot command for agents/CI rather than running the three elements separately.

```bash
reveal cpanel://myuser/full-audit
```

```
Full audit: myuser
===================

❌ SSL (9 domains): 1 expired, 3 critical, 1 error, 1 expiring, 1 missing, 2 ok
     expired.example.com: ❌ EXPIRED 5d ago  (2026-10-23)
     critical.example.com: ⚠️  3d  (2026-10-31)
     ...
     nocert.example.com: ⚫ no cert at /var/cpanel/ssl/apache_tls/nocert.example.com/combined
❌ ACL (9 domains): 8 ok, 1 denied
     shop.example.com: ❌ denied  (/home/myuser/public_html)
✅ nginx ACME (1 domains): 1 ok

❌ Audit complete — failures detected (exit 2)
```

Any SSL status other than `ok` fails the audit, including `expiring` and `missing`. The nginx section fails on an ACL denial or a failing live certificate. When everything passes the last line reads `✅ Audit complete — all checks passed` and the exit code is 0.

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

See [NGINX_GUIDE.md](NGINX_GUIDE.md) for all nginx operator commands.

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
| `--dns-verified` | `ssl`, `full-audit` | Exclude NXDOMAIN and elsewhere-resolving domains from summary counts |
| `--only-failures` | `ssl`, `acl-check`, `full-audit` | Show only non-ok/denied entries |
| `--check-live` | `ssl` | For each non-ok disk cert, fetch the live cert and show its expiry (catches CDN/edge renewals where the disk cert is stale) |
| `?domain_type=<type>` | `ssl` | Filter to one domain type, e.g. `?domain_type=subdomain` |
| `--format=json` | all | JSON output for scripting |

---

## See Also

- `reveal help://cpanel` — inline help with live examples
- [NGINX_GUIDE.md](NGINX_GUIDE.md) — all nginx operator flags
- [SSL_ADAPTER_GUIDE.md](SSL_ADAPTER_GUIDE.md) — live SSL certificate inspection
- `reveal /etc/nginx/conf.d/users/USERNAME.conf --validate-nginx-acme` — full audit
- `reveal /etc/nginx/conf.d/users/USERNAME.conf --cpanel-certs` — disk vs live comparison
