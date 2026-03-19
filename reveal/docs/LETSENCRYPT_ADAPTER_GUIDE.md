---
title: "Let's Encrypt Adapter Guide (letsencrypt://)"
type: guide
beth_topics:
  - reveal
  - letsencrypt
  - ssl
  - certificate
  - nginx
---
# Let's Encrypt Adapter Guide (`letsencrypt://`)

Inspect your Let's Encrypt certificate inventory, find orphaned certs no longer
referenced by nginx, and detect duplicate-SAN certs that waste renewal cycles.

---

## Overview

The `letsencrypt://` adapter reads `/etc/letsencrypt/live/*/cert.pem` — the
standard certbot live directory — and surfaces:

- **Inventory**: all managed certs with SANs, expiry, and common name
- **Orphan detection** (`--check-orphans`): certs present on disk but not
  referenced by any `ssl_certificate` directive in nginx
- **Duplicate-SAN detection** (`--check-duplicates`): certs that cover identical
  hostnames — usually left-over from a rename or migration

> **Requirements**: read access to `/etc/letsencrypt/live/` (usually requires
> `root` or the `ssl-cert` group). Orphan detection also requires read access to
> `/etc/nginx/sites-enabled/` and `/etc/nginx/conf.d/`.

---

## Quick Start

```bash
# Full cert inventory
reveal letsencrypt://

# Find certs not in use by any nginx vhost
reveal letsencrypt:// --check-orphans

# Find certs covering duplicate hostnames
reveal letsencrypt:// --check-duplicates

# Run both checks at once
reveal letsencrypt:// --check-orphans --check-duplicates

# Machine-readable output
reveal letsencrypt:// --format json
```

---

## Example Output

### Cert inventory

```
  name                  common name            expiry     SANs
  ──────────────────────────────────────────────────────────────
  mytia.net             mytia.net              87d        3 name(s)
  api.mytia.net         api.mytia.net          87d        1 name(s)
  old-app.example.com   old-app.example.com    EXPIRED    1 name(s)

  reveal letsencrypt:// --check-orphans    # find unreferenced certs
  # 1 cert(s) are EXPIRED — renew with: certbot renew
```

### Orphan check

```
Orphan check (nginx dirs: /etc/nginx/sites-enabled, /etc/nginx/conf.d)
  ssl_certificate paths found in nginx: 4
  ❌ 1 orphaned cert(s) (not referenced by any ssl_certificate):
    old-app.example.com  (EXPIRED (12d ago))  /etc/letsencrypt/live/old-app.example.com/cert.pem
```

### Duplicate-SAN check

```
Duplicate SAN check
  ⚠️  1 group(s) with identical SANs:
    SANs: example.com, www.example.com
      example.com-old                  87d
      example.com                      87d
```

---

## Expiry Labels

| Label | Meaning |
|-------|---------|
| `87d` | Healthy — more than 30 days remaining |
| `~14d` | Warning — 8–30 days remaining |
| `⚠️  5d` | Urgent — 7 days or fewer remaining |
| `EXPIRED (3d ago)` | Certificate has expired |

---

## Flags Reference

| Flag | Description |
|------|-------------|
| `--check-orphans` | Cross-reference certs against nginx `ssl_certificate` directives |
| `--check-duplicates` | Find certs with identical SAN sets |
| `--format json` | JSON output (full structured result) |

Both checks can be combined in a single call.

---

## How Orphan Detection Works

When `--check-orphans` is passed, the adapter:

1. Scans `/etc/nginx/sites-enabled/` and `/etc/nginx/conf.d/` for all
   `ssl_certificate` directives
2. Collects the referenced cert paths (e.g.
   `/etc/letsencrypt/live/example.com/fullchain.pem`)
3. For each cert in the inventory, checks whether its parent directory appears
   in any referenced path — covering both `cert.pem` and `fullchain.pem` usage
4. Reports certs whose directory is never referenced

A cert is considered **in use** if any nginx `ssl_certificate` value starts with
`/etc/letsencrypt/live/CERTNAME/`. This handles all certbot-issued file variants
(`cert.pem`, `chain.pem`, `fullchain.pem`, `privkey.pem`) without requiring an
exact filename match.

---

## JSON Output

```bash
reveal letsencrypt:// --check-orphans --check-duplicates --format json | jq .
```

Key fields in the JSON response:

```json
{
  "type": "letsencrypt_inventory",
  "live_dir": "/etc/letsencrypt/live",
  "live_dir_exists": true,
  "cert_count": 3,
  "certs": [
    {
      "name": "mytia.net",
      "cert_path": "/etc/letsencrypt/live/mytia.net/cert.pem",
      "common_name": "mytia.net",
      "san": ["mytia.net", "www.mytia.net", "api.mytia.net"],
      "days_until_expiry": 87,
      "not_after": "2026-06-14T12:00:00",
      "is_expired": false,
      "issuer": "Let's Encrypt"
    }
  ],
  "orphan_check": {
    "nginx_dirs_scanned": ["/etc/nginx/sites-enabled", "/etc/nginx/conf.d"],
    "nginx_cert_paths_found": 4,
    "orphan_count": 0,
    "orphans": []
  },
  "duplicate_check": {
    "duplicate_group_count": 0,
    "groups": []
  },
  "next_steps": []
}
```

---

## Workflows

### Cert health sweep before deploying

```bash
# On the server — catch expired or near-expiry certs
reveal letsencrypt:// --check-orphans --check-duplicates

# JSON for automation / CI
reveal letsencrypt:// --format json | jq '.certs[] | select(.days_until_expiry < 30)'
```

### Clean up after a domain migration

After migrating a domain and updating nginx:

```bash
reveal letsencrypt:// --check-orphans
# → shows old-domain cert as orphaned
# → safe to delete: certbot delete --cert-name old-domain.example.com
```

### Find renewal candidates after a hostname consolidation

```bash
reveal letsencrypt:// --check-duplicates
# → two certs for example.com with identical SANs
# → one is a stale rename artifact → delete the older one
```

---

## Limitations

- **Read-only**: no cert issuance, renewal, or revocation. Use `certbot` directly.
- **certbot live dir only**: reads `/etc/letsencrypt/live/` — does not inspect
  ACME staging or custom cert stores.
- **nginx only**: orphan detection scans nginx config dirs. Apache, Caddy, or
  other servers are not checked.
- **No OCSP revocation check**: expiry and SANs only. Revocation status requires
  `ssl://` with `--health` flags.

---

## Troubleshooting

**`/etc/letsencrypt/live not found`**

The adapter prints a warning and exits cleanly. This is expected on a server
that doesn't use certbot. Run as `root` or a user with read access to that path.

**Cert shows no SANs / error field**

The cert.pem could not be parsed (corrupted, wrong format, or missing). The cert
entry will have an `error` key in JSON output instead of `san`/`expiry` fields.

**All certs show as orphaned**

nginx may be using a non-standard config directory or `fullchain.pem` at a custom
path (e.g. via `ssl_certificate_key` referencing a copied cert). Inspect the raw
nginx config to see what paths are in use:

```bash
grep -r ssl_certificate /etc/nginx/ | grep -v ssl_certificate_key
```

---

## See Also

- [SSL_ADAPTER_GUIDE.md](SSL_ADAPTER_GUIDE.md) — live TLS endpoint checks (expiry, chain, health)
- [NGINX_GUIDE.md](NGINX_GUIDE.md) — nginx config analysis, ACME validation, fleet audit
- [CPANEL_ADAPTER_GUIDE.md](CPANEL_ADAPTER_GUIDE.md) — cPanel AutoSSL and SSL disk health

---

**Navigation**: [Index](README.md) | [Adapter Guides](INDEX.md#adapter-guides-18-files)
