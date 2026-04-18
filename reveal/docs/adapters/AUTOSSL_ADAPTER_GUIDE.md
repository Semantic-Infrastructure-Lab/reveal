---
title: "AutoSSL Adapter Guide (autossl://)"
type: guide
beth_topics:
  - reveal
  - autossl
  - ssl
  - cpanel
  - certificate
  - dcv
---
# AutoSSL Adapter Guide (`autossl://`)

Inspect cPanel AutoSSL run logs to diagnose TLS renewal failures — per-domain
outcomes, defect codes, DCV impediments, and chronic failure detection.
Filesystem-based: no WHM API or credentials required.

---

## Overview

The `autossl://` adapter parses the NDJSON logs written by cPanel AutoSSL at
`/var/cpanel/logs/autossl/`. It surfaces:

- **Run inventory**: all available run timestamps (newest first)
- **Per-domain TLS status**: `ok`, `incomplete`, or `defective`
- **Defect codes**: `SELF_SIGNED_CERT`, `CERT_HAS_EXPIRED`, etc.
- **DCV impediment codes**: `TOTAL_DCV_FAILURE`, `DNS_RESOLVES_TO_ANOTHER_SERVER`, etc.
- **User-scoped output**: filter to one cPanel user — essential on shared hosts
  with hundreds of domains
- **Domain history**: TLS status across all runs — detects chronic failures

> **Requirements**: read access to `/var/cpanel/logs/autossl/` — usually requires
> `root`. AutoSSL runs approximately every 3 hours; logs are retained ~30 days.

---

## Quick Start

```bash
# List available run timestamps
reveal autossl://

# Most recent run — full summary
reveal autossl://latest

# Failures only — fastest triage view
reveal 'autossl://latest?only-failures'

# Scope to one cPanel user (avoids 800-domain output on shared hosts)
reveal 'autossl://latest?user=myuser&only-failures'

# Aggregated counts only — quickest overview
reveal 'autossl://latest?summary'

# Domain history across all runs
reveal autossl://app.example.com

# Parse a specific run by timestamp
reveal autossl://2026-03-03T23:26:01Z

# Machine-readable output
reveal autossl://latest --format=json
```

---

## Flags Reference

| Flag | URI query param | Description |
|------|----------------|-------------|
| `--only-failures` | `?only-failures` | Show only domains with `defective` or `incomplete` status |
| `--summary` | `?summary` | Aggregated counts only — no per-domain rows |
| `--user=NAME` | `?user=NAME` | Filter to a single cPanel username |
| `--all` | — | Domain history: show all runs (bypasses default 20-run cap) |
| `--format=json` | — | Full structured JSON output |

The URI query param form is preferred for pipelines — options travel with the
resource string and compose naturally:

```bash
reveal 'autossl://latest?user=sociamonials&only-failures'
```

---

## TLS Status Values

| Status | Meaning |
|--------|---------|
| `ok` | Certificate valid; AutoSSL satisfied — no renewal needed |
| `incomplete` | No renewal triggered — existing cert still valid, not near expiry |
| `defective` | Certificate has a problem: expired, self-signed, or chain error |

---

## Defect Codes

These appear in the `defect_code` field when `tls_status == "defective"`.

| Code | Meaning | Fix |
|------|---------|-----|
| `DEPTH_ZERO_SELF_SIGNED_CERT` | Leaf cert is self-signed (cPanel fallback) | AutoSSL should replace automatically; check DCV if stuck |
| `SELF_SIGNED_CERT_IN_CHAIN` | Chain includes a self-signed intermediate | Re-run AutoSSL; inspect chain with `reveal ssl://DOMAIN --advanced` |
| `CERT_HAS_EXPIRED` | Certificate has passed its `notAfter` date | Fix DCV impediments — see table below |
| `UNABLE_TO_GET_ISSUER_CERT_LOCALLY` | Issuer cert missing from local trust store | Usually resolves next cycle; check with `reveal ssl://DOMAIN --advanced` |
| `CERTIFICATE_VERIFY_FAILED` | General chain validation error | Inspect live cert: `reveal ssl://DOMAIN --advanced` |

---

## DCV Impediment Codes

These appear when AutoSSL cannot complete domain control validation. A domain
must pass DCV for AutoSSL to issue or renew its certificate.

| Code | Meaning | Fix |
|------|---------|-----|
| `TOTAL_DCV_FAILURE` | Every domain in the cert failed DCV | Verify DNS A record points to this server; check ACME path: `reveal nginx://DOMAIN --validate-nginx-acme` |
| `NO_UNSECURED_DOMAIN_PASSED_DCV` | All domains failed DCV — at least one must pass | Fix the primary domain DCV first; subdomains inherit |
| `DNS_RESOLVES_TO_ANOTHER_SERVER` | Domain's DNS points elsewhere — AutoSSL skips it | Update DNS to point here, or remove the domain from cPanel; check with `reveal domain://DOMAIN` |
| `DOMAIN_NOT_IN_CPANEL` | Domain not found in the cPanel account | Re-add the domain to cPanel or remove it from the cert |

---

## Workflows

### Failure triage on a shared host

```bash
# 1. See what runs are available
reveal autossl://

# 2. Get the latest summary — failures only
reveal 'autossl://latest?only-failures'

# 3. Scope to one user to reduce noise
reveal 'autossl://latest?user=myuser&only-failures'

# 4. Extract defective domains as JSON for scripting
reveal autossl://latest --format=json | jq '[.users[].domains[] | select(.tls_status=="defective")]'
```

### Investigate a chronically failing domain

```bash
# Domain history — last 20 runs; "Failing since: DATE" shows if no run succeeded
reveal autossl://app.example.com

# Full history (all runs)
reveal autossl://app.example.com --all

# Inspect the live cert
reveal ssl://app.example.com --advanced

# Check DNS
reveal domain://app.example.com

# Verify ACME challenge path is accessible
reveal nginx://app.example.com --validate-nginx-acme
```

### Post-migration validation

After migrating a domain to a new server:

```bash
# Check if AutoSSL picked it up on the new server
reveal 'autossl://latest?user=myuser'

# If DNS_RESOLVES_TO_ANOTHER_SERVER appears on the old server, that's expected
reveal autossl://old-domain.example.com   # confirm it's only failing on the old host
```

### CI / monitoring pipeline

```bash
# Fail if any defective domains exist
reveal autossl://latest --format=json | \
  jq -e '[.users[].domains[] | select(.tls_status=="defective")] | length == 0'
```

---

## JSON Output

```bash
reveal autossl://latest --format=json | jq .
```

Key fields:

```json
{
  "type": "autossl_run",
  "timestamp": "2026-03-03T23:26:01Z",
  "user_count": 3,
  "domain_count": 847,
  "users": [
    {
      "username": "sociamonials",
      "domains": [
        {
          "domain": "app.example.com",
          "tls_status": "defective",
          "defect_code": "CERT_HAS_EXPIRED",
          "dcv_impediment": "TOTAL_DCV_FAILURE"
        }
      ]
    }
  ],
  "summary": {
    "ok": 820,
    "incomplete": 24,
    "defective": 3
  }
}
```

---

## Limitations

- **Read-only**: no cert issuance or renewal. Trigger AutoSSL via WHM or `whmapi1 start_autossl_check`.
- **cPanel only**: reads `/var/cpanel/logs/autossl/` — not applicable to plain Linux + certbot setups. Use `reveal letsencrypt://` for certbot-managed certs.
- **Root required**: log files are not world-readable on most installations.
- **No live cert data**: reports AutoSSL's logged judgment, not the live TLS endpoint. Follow up with `reveal ssl://DOMAIN` for real-time cert state.

---

## Troubleshooting

**`/var/cpanel/logs/autossl not found`**

Not a cPanel server, or running without root access. This adapter is cPanel-specific.

**All domains show `incomplete`**

AutoSSL ran but found all certs healthy and not near expiry — this is normal. No renewal was needed. Check `days_until_expiry` with `reveal ssl://DOMAIN`.

**`defective` domains persist after fixing DNS**

AutoSSL runs every ~3 hours. Wait for the next cycle, or trigger a manual run in WHM. Confirm fix with `reveal domain://DOMAIN` (DNS) and `reveal autossl://DOMAIN` (history).

---

## See Also

- [SSL_ADAPTER_GUIDE.md](SSL_ADAPTER_GUIDE.md) — live TLS endpoint inspection (expiry, chain, health)
- [NGINX_GUIDE.md](NGINX_GUIDE.md) — ACME challenge path validation, nginx config analysis
- [CPANEL_ADAPTER_GUIDE.md](CPANEL_ADAPTER_GUIDE.md) — cPanel user overview and disk cert health
- [LETSENCRYPT_ADAPTER_GUIDE.md](LETSENCRYPT_ADAPTER_GUIDE.md) — certbot-managed cert inventory and orphan detection

---

**Navigation**: [Index](../README.md) | [Adapter Guides](../INDEX.md#adapter-guides-19-files)
