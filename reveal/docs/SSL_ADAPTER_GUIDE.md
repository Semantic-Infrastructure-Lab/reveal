# SSL Adapter Guide

**Author**: TIA (The Intelligent Agent)
**Created**: 2025-02-14
**Adapter**: `ssl://`
**Purpose**: SSL/TLS certificate inspection and health monitoring

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Core Concepts](#core-concepts)
4. [Progressive Disclosure Pattern](#progressive-disclosure-pattern)
5. [Health Check System](#health-check-system)
6. [Certificate Elements](#certificate-elements)
7. [Batch Processing](#batch-processing)
8. [Workflows](#workflows)
9. [Integration Examples](#integration-examples)
10. [Security Considerations](#security-considerations)
11. [Performance & Best Practices](#performance--best-practices)
12. [Limitations](#limitations)
13. [Troubleshooting](#troubleshooting)
14. [Tips & Tricks](#tips--tricks)
15. [Related Documentation](#related-documentation)
16. [FAQ](#faq)
17. [Version History](#version-history)

---

## Overview

The **ssl adapter** (`ssl://`) provides SSL/TLS certificate inspection with:

- **Progressive disclosure** - Overview → elements → health checks (token-efficient)
- **Health monitoring** - Expiry warnings, chain validation, hostname matching
- **Batch processing** - Check multiple domains from nginx configs or stdin
- **Zero dependencies** - Uses Python's built-in `ssl` module
- **Exit codes** - Machine-readable status (0=pass, 1=warning, 2=critical)

### Key Features

- ✅ **Progressive disclosure** - Start with overview, drill down to details
- ✅ **Health checks** - Expiry thresholds (30/7 days), chain validation, hostname match
- ✅ **Batch mode** - Check multiple domains at once (nginx, stdin)
- ✅ **Advanced checks** - TLS version, key strength, self-signed detection
- ✅ **Zero external dependencies** - Pure Python `ssl` module
- ✅ **Exit codes** - 0=healthy, 1=warning, 2=critical (CI/CD friendly)

### When to Use

**Use ssl:// when you need to**:
- Check certificate expiry before renewal
- Debug SSL/TLS connection issues
- Audit SSL certificates across infrastructure
- Monitor certificate health in production
- Validate nginx SSL configuration
- Troubleshoot browser certificate warnings

**Don't use ssl:// when**:
- You need OCSP/revocation checking (use openssl s_client)
- You need detailed cryptographic analysis (use openssl x509)
- You need to generate/modify certificates (use openssl req/x509)

---

## Quick Start

### Example 1: Certificate Overview

Get certificate summary (issuer, expiry, health):

```bash
reveal ssl://example.com
```

**Output**:
```
SSL Certificate: example.com:443
  Common Name: example.com
  Issuer: Let's Encrypt
  Valid: 2026-01-01 → 2026-04-01 (54 days remaining)
  Health: ✅ HEALTHY
  Domains: 2 (example.com, www.example.com)

Next steps:
  reveal ssl://example.com/san      # View all domain names
  reveal ssl://example.com/issuer   # Issuer details
  reveal ssl://example.com --check  # Run health checks
```

### Example 2: Non-Standard Port

Check certificate on custom port:

```bash
reveal ssl://example.com:8443
```

### Example 3: Health Check

Run comprehensive health checks:

```bash
reveal ssl://example.com --check
```

**Output**:
```
SSL Health Check: example.com:443

Status: ✅ PASS

Checks:
  ✅ Certificate valid (not expired)
  ✅ Expires in 54 days (threshold: 30 days)
  ✅ Certificate chain valid
  ✅ Hostname matches certificate

Certificate:
  Common Name: example.com
  Issuer: Let's Encrypt
  Valid until: 2026-04-01
```

### Example 4: Advanced Health Check

Run advanced checks (TLS version, key strength, self-signed detection):

```bash
reveal ssl://example.com --check --advanced
```

**Output**:
```
SSL Health Check: example.com:443

Status: ✅ PASS

Basic Checks:
  ✅ Certificate valid
  ✅ Expires in 54 days
  ✅ Certificate chain valid
  ✅ Hostname matches

Advanced Checks:
  ✅ TLS version: TLSv1.3 (secure)
  ✅ Key strength: RSA 2048-bit (adequate)
  ✅ Issuer type: Trusted CA (Let's Encrypt)
  ✅ Not self-signed
```

### Example 5: View Subject Alternative Names (SANs)

See all domains covered by certificate:

```bash
reveal ssl://example.com/san
```

**Output**:
```
Subject Alternative Names: example.com

Common Name: example.com
Domains (2):
  - example.com
  - www.example.com
```

### Example 6: View Certificate Chain

Inspect certificate chain (intermediate + root):

```bash
reveal ssl://example.com/chain
```

**Output**:
```
Certificate Chain: example.com

Leaf Certificate:
  Common Name: example.com
  Issuer: R3 (Let's Encrypt)

Chain (2 certificates):
  1. R3 (Let's Encrypt)
     Issuer: ISRG Root X1
  2. ISRG Root X1 (Self-signed root)
```

### Example 7: Batch Check from File

Check multiple domains:

```bash
# Create domains list
cat > domains.txt <<EOF
ssl://example.com
ssl://google.com
ssl://github.com
EOF

# Batch check
reveal --stdin --check < domains.txt
```

### Example 8: Nginx SSL Audit

Audit all SSL certificates from nginx config:

```bash
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --summary
```

**Output**:
```
SSL Batch Check: /etc/nginx/conf.d/*.conf

Status: ⚠️  WARNING

Summary:
  Total: 12 domains
  ✅ Passed: 10
  ⚠️  Warnings: 2 (expiring <30 days)
  ❌ Failures: 0

Next steps:
  reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --only-failures
```

---

## Core Concepts

### 1. Progressive Disclosure

SSL adapter uses **progressive disclosure** to minimize token usage:

**Pattern**:
1. **Overview** (`ssl://example.com`) - 150 tokens
2. **Element** (`ssl://example.com/san`) - 50-100 tokens
3. **Health check** (`ssl://example.com --check`) - 200-300 tokens

**Workflow**:
```bash
# Start with overview (quick assessment)
reveal ssl://example.com

# Drill down if needed
reveal ssl://example.com/san     # Check domain coverage
reveal ssl://example.com/chain   # Inspect chain

# Run health checks when issues found
reveal ssl://example.com --check --advanced
```

### 2. Health Status Levels

| Status | Threshold | Icon | Description |
|--------|-----------|------|-------------|
| **HEALTHY** | >30 days | ✅ | Certificate is valid and not expiring soon |
| **WARNING** | 7-30 days | ⚠️ | Certificate expires soon (renew recommended) |
| **CRITICAL** | 0-7 days | ❌ | Certificate expires very soon (urgent renewal) |
| **EXPIRED** | <0 days | ❌ | Certificate has expired (immediate action required) |

### 3. Exit Codes

SSL adapter returns machine-readable exit codes:

| Exit Code | Status | Use Case |
|-----------|--------|----------|
| `0` | Healthy | CI/CD passed, no issues |
| `1` | Warning | Certificate expiring <30 days |
| `2` | Critical | Certificate expiring <7 days or failed checks |

**CI/CD usage**:
```bash
if reveal ssl://example.com --check; then
  echo "✅ SSL certificate healthy"
else
  echo "❌ SSL certificate issues detected"
  exit 1
fi
```

### 4. Verification vs Diagnostics

SSL adapter performs **two separate operations**:

**1. Diagnostic Connection** (no verification):
- Connects to retrieve certificate
- Does NOT validate chain
- Purpose: Get certificate details even if invalid

**2. Separate Verification**:
- Validates against system trust store
- Checks hostname match
- Checks chain validity
- Reports verification result separately

**Why this design?**
- Can inspect invalid certificates (debugging)
- Clear separation: "What cert exists?" vs "Is cert valid?"

---

## Progressive Disclosure Pattern

### Overview Level

**Command**: `ssl://example.com`

**Returns** (~150 tokens):
- Common name
- Issuer
- Validity dates
- Days until expiry
- Health status
- SAN count
- Next steps

**When to use**: Quick assessment, initial triage

### Element Level

**Commands**:
- `ssl://example.com/san` - Domain names (50 tokens)
- `ssl://example.com/chain` - Certificate chain (100 tokens)
- `ssl://example.com/issuer` - Issuer details (50 tokens)
- `ssl://example.com/subject` - Subject details (50 tokens)
- `ssl://example.com/dates` - Validity dates (30 tokens)
- `ssl://example.com/full` - Complete dump (500+ tokens)

**When to use**: Focused investigation (e.g., check if SAN covers subdomain)

### Health Check Level

**Commands**:
- `ssl://example.com --check` - Basic checks (200 tokens)
- `ssl://example.com --check --advanced` - Advanced checks (300 tokens)

**When to use**: Validation, CI/CD, monitoring

---

## Health Check System

### Basic Health Checks

**Enabled with**: `--check`

**Checks performed**:
1. **Expiry check** - Is certificate valid (not expired)?
2. **Expiry warning** - Does certificate expire within 30 days?
3. **Chain validation** - Is certificate chain valid against system trust store?
4. **Hostname match** - Does certificate CN/SAN match requested hostname?

**Example**:
```bash
reveal ssl://example.com --check
```

### Advanced Health Checks

**Enabled with**: `--check --advanced`

**Additional checks**:
1. **TLS version** - Is TLS 1.2+ used (not SSL/TLS 1.0/1.1)?
2. **Key strength** - Is key size adequate (RSA 2048+, ECDSA 256+)?
3. **Issuer type** - Is issuer a trusted CA (not self-signed)?
4. **Self-signed detection** - Is certificate self-signed?

**Example**:
```bash
reveal ssl://example.com --check --advanced
```

### Custom Expiry Thresholds

**Adjust warning/critical thresholds**:

```bash
# Warn at 60 days, critical at 14 days
reveal ssl://example.com --check --warn-days=60 --critical-days=14
```

**Default thresholds**:
- Warning: 30 days
- Critical: 7 days

---

## Certificate Elements

### san - Subject Alternative Names

**Description**: All domain names covered by certificate

**Command**:
```bash
reveal ssl://example.com/san
```

**Output**:
```json
{
  "type": "ssl_san",
  "host": "example.com",
  "common_name": "example.com",
  "san": ["example.com", "www.example.com", "*.example.com"],
  "san_count": 3,
  "wildcard_entries": ["*.example.com"]
}
```

**Use cases**:
- Check if subdomain is covered
- Verify wildcard coverage
- Audit domain list

### chain - Certificate Chain

**Description**: Certificate chain (intermediate + root certificates)

**Command**:
```bash
reveal ssl://example.com/chain
```

**Output**:
```json
{
  "type": "ssl_chain",
  "host": "example.com",
  "leaf": {
    "common_name": "example.com",
    "issuer": "R3"
  },
  "chain": [
    {
      "common_name": "R3",
      "issuer": "ISRG Root X1",
      "valid_until": "2025-09-15"
    },
    {
      "common_name": "ISRG Root X1",
      "issuer": "ISRG Root X1",
      "valid_until": "2035-06-04"
    }
  ],
  "chain_length": 3,
  "verification": {
    "chain_valid": true,
    "error": null
  }
}
```

**Use cases**:
- Debug chain validation issues
- Verify intermediate cert presence
- Check root CA

### issuer - Issuer Details

**Description**: Certificate issuer information

**Command**:
```bash
reveal ssl://example.com/issuer
```

**Output**:
```json
{
  "type": "ssl_issuer",
  "host": "example.com",
  "issuer_name": "Let's Encrypt",
  "issuer": {
    "commonName": "R3",
    "organizationName": "Let's Encrypt",
    "countryName": "US"
  }
}
```

**Use cases**:
- Verify CA identity
- Check issuer organization
- Audit certificate sources

### subject - Subject Details

**Description**: Certificate subject information

**Command**:
```bash
reveal ssl://example.com/subject
```

**Output**:
```json
{
  "type": "ssl_subject",
  "host": "example.com",
  "common_name": "example.com",
  "subject": {
    "commonName": "example.com"
  }
}
```

### dates - Validity Dates

**Description**: Certificate validity period

**Command**:
```bash
reveal ssl://example.com/dates
```

**Output**:
```json
{
  "type": "ssl_dates",
  "host": "example.com",
  "not_before": "2026-01-01T00:00:00Z",
  "not_after": "2026-04-01T23:59:59Z",
  "days_until_expiry": 54,
  "is_expired": false
}
```

### full - Complete Certificate

**Description**: Full certificate dump (all fields)

**Command**:
```bash
reveal ssl://example.com/full --format=json
```

**Warning**: Large output (500+ lines). Use sparingly.

---

## Batch Processing

### Method 1: Nginx Config Mode

**Syntax**: `ssl://nginx:///path/to/config`

**Description**: Automatically extract SSL domains from nginx config and check them.

**Examples**:

**Basic batch check**:
```bash
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check
```

**Summary only** (counts, no details):
```bash
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --summary
```

**Show only failures**:
```bash
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --only-failures
```

**Validate nginx config against actual certificates**:
```bash
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --validate-nginx
```

### Method 2: Stdin Mode

**Syntax**: `reveal --stdin --check < file.txt`

**Description**: Read `ssl://` URIs from stdin (one per line).

**Examples**:

**From file**:
```bash
cat domains.txt | reveal --stdin --check
```

**From command**:
```bash
echo -e "ssl://example.com\nssl://google.com" | reveal --stdin --check
```

**With preprocessing**:
```bash
# Extract domains, convert to ssl:// URIs, check
cat nginx.conf | grep server_name | awk '{print $2}' | sed 's/^/ssl:\/\//' | reveal --stdin --check
```

**Filter expiring certificates**:
```bash
reveal --stdin --check --expiring-within=30 < domains.txt
```

### Method 3: Composable Pipeline

**Syntax**: `reveal nginx.conf --extract domains | reveal --stdin --check`

**Description**: Two-stage pipeline (extract → check) for custom filtering.

**Examples**:

**Basic pipeline**:
```bash
reveal nginx.conf --extract domains | reveal --stdin --check
```

**Filter between stages**:
```bash
# Check only production domains
reveal nginx.conf --extract domains | grep prod | reveal --stdin --check

# Exclude staging domains
reveal nginx.conf --extract domains | grep -v staging | reveal --stdin --check
```

**Combined with other filters**:
```bash
reveal nginx.conf --extract domains | sort | uniq | reveal --stdin --check --only-failures
```

### Batch Output Options

| Flag | Effect |
|------|--------|
| `--check` | Run health checks on all domains |
| `--summary` | Show aggregated counts only (no per-domain details) |
| `--only-failures` | Hide healthy results, show warnings/failures only |
| `--expiring-within=N` | Filter to certificates expiring within N days |
| `--advanced` | Run advanced checks (TLS version, key strength, etc.) |

---

## Workflows

### Workflow 1: Monitor Certificate Expiry

**Scenario**: Regular monitoring to catch expiring certificates.

**Steps**:

1. **Check all certificates**:
   ```bash
   reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check
   ```

2. **Filter to expiring certificates**:
   ```bash
   reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --expiring-within=30
   ```

3. **Show only problems**:
   ```bash
   reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --only-failures
   ```

4. **Inspect specific certificate**:
   ```bash
   reveal ssl://expiring-domain.com --check --advanced
   ```

**Automation** (cron job):
```bash
#!/bin/bash
# /etc/cron.daily/check-ssl-certs

REPORT="/var/log/ssl-check-$(date +%Y-%m-%d).txt"

reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --only-failures > "$REPORT"

if [ -s "$REPORT" ]; then
  mail -s "SSL Certificate Warnings" admin@example.com < "$REPORT"
fi
```

### Workflow 2: Debug SSL Connection Issues

**Scenario**: Users reporting "Certificate error" in browser.

**Steps**:

1. **Quick overview**:
   ```bash
   reveal ssl://example.com
   ```

2. **Run basic health check**:
   ```bash
   reveal ssl://example.com --check
   ```

3. **Check certificate chain** (most common issue):
   ```bash
   reveal ssl://example.com/chain
   ```

4. **Check hostname match** (if SAN mismatch suspected):
   ```bash
   reveal ssl://example.com/san
   ```

5. **Run advanced checks** (if TLS version or key strength suspected):
   ```bash
   reveal ssl://example.com --check --advanced
   ```

**Common findings**:
- Expired certificate → Renew immediately
- Chain invalid → Missing intermediate certificate
- Hostname mismatch → SAN doesn't cover subdomain
- TLS 1.0/1.1 → Outdated protocol (upgrade required)

### Workflow 3: Pre-Deployment SSL Validation

**Scenario**: Validate SSL configuration before deploying new site.

**Steps**:

1. **Check certificate exists**:
   ```bash
   reveal ssl://new-site.com
   ```

2. **Validate health**:
   ```bash
   reveal ssl://new-site.com --check --advanced
   ```

3. **Verify SAN coverage**:
   ```bash
   reveal ssl://new-site.com/san
   # Confirm www., api., and other subdomains are covered
   ```

4. **Check nginx config alignment**:
   ```bash
   reveal ssl://nginx:///etc/nginx/sites-enabled/new-site.conf --check --validate-nginx
   ```

5. **Test from multiple locations** (geographic DNS):
   ```bash
   ssh server-us "reveal ssl://new-site.com --check"
   ssh server-eu "reveal ssl://new-site.com --check"
   ssh server-asia "reveal ssl://new-site.com --check"
   ```

### Workflow 4: SSL Certificate Audit

**Scenario**: Quarterly audit of all SSL certificates.

**Steps**:

1. **Generate inventory**:
   ```bash
   reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --format=json > ssl-audit.json
   ```

2. **Extract statistics**:
   ```bash
   jq '.summary' ssl-audit.json
   ```

3. **List expiring certificates** (<60 days):
   ```bash
   reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --expiring-within=60 --format=json | \
     jq '.results[] | select(.days_until_expiry < 60) | {domain: .host, days: .days_until_expiry}'
   ```

4. **Check issuer diversity**:
   ```bash
   jq -r '.results[] | .issuer' ssl-audit.json | sort | uniq -c
   ```

5. **Identify weak certificates** (non-2048+ keys, old TLS):
   ```bash
   reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --advanced --only-failures
   ```

### Workflow 5: CI/CD SSL Validation

**Scenario**: Validate SSL certificates in deployment pipeline.

**Steps**:

**GitHub Actions workflow** (`.github/workflows/ssl-check.yml`):
```yaml
name: SSL Certificate Check

on:
  schedule:
    - cron: '0 0 * * *'  # Daily at midnight
  workflow_dispatch:

jobs:
  check-ssl:
    runs-on: ubuntu-latest
    steps:
      - name: Install reveal
        run: pip install reveal-toolkit

      - name: Check production certificates
        run: |
          echo "ssl://example.com" > domains.txt
          echo "ssl://www.example.com" >> domains.txt
          echo "ssl://api.example.com" >> domains.txt

          reveal --stdin --check < domains.txt

      - name: Check expiring soon
        run: |
          if reveal --stdin --check --expiring-within=30 < domains.txt; then
            echo "✅ No certificates expiring within 30 days"
          else
            echo "⚠️  Certificates expiring soon!"
            exit 1
          fi
```

### Workflow 6: Bulk Certificate Renewal Planning

**Scenario**: Plan certificate renewals for infrastructure.

**Steps**:

1. **Get all certificates with expiry dates**:
   ```bash
   reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --format=json > certs.json
   ```

2. **Group by expiry window**:
   ```bash
   # Expiring in 0-7 days (urgent)
   jq '.results[] | select(.days_until_expiry >= 0 and .days_until_expiry < 7)' certs.json

   # Expiring in 7-30 days (soon)
   jq '.results[] | select(.days_until_expiry >= 7 and .days_until_expiry < 30)' certs.json

   # Expiring in 30-60 days (plan ahead)
   jq '.results[] | select(.days_until_expiry >= 30 and .days_until_expiry < 60)' certs.json
   ```

3. **Generate renewal schedule**:
   ```bash
   jq -r '.results[] | select(.days_until_expiry < 60) |
     "\(.host)\t\(.days_until_expiry) days\t\(.valid_until)"' certs.json | \
     sort -t$'\t' -k2 -n > renewal-schedule.txt
   ```

4. **Send report**:
   ```bash
   mail -s "SSL Renewal Schedule" ops@example.com < renewal-schedule.txt
   ```

---

## Integration Examples

### 1. jq - JSON Processing

**Extract specific fields**:
```bash
# Get all domains and expiry dates
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --format=json | \
  jq -r '.results[] | "\(.host): \(.days_until_expiry) days"'

# Count by status
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --format=json | \
  jq '.summary'

# List only critical certificates
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --format=json | \
  jq '.results[] | select(.status == "failure")'
```

### 2. Python - Certificate Analysis

**Example: Generate HTML report**:
```python
import json
import subprocess
from datetime import datetime

# Get SSL check results
result = subprocess.run(
    ['reveal', 'ssl://nginx:///etc/nginx/conf.d/*.conf', '--check', '--format=json'],
    capture_output=True, text=True
)
data = json.loads(result.stdout)

# Generate HTML report
html = f"""
<html>
<head><title>SSL Certificate Report</title></head>
<body>
  <h1>SSL Certificate Report</h1>
  <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

  <h2>Summary</h2>
  <ul>
    <li>Total: {data['summary']['total']}</li>
    <li>Passed: {data['summary']['passed']}</li>
    <li>Warnings: {data['summary']['warnings']}</li>
    <li>Failures: {data['summary']['failures']}</li>
  </ul>

  <h2>Certificates</h2>
  <table border="1">
    <tr>
      <th>Domain</th>
      <th>Status</th>
      <th>Days Until Expiry</th>
      <th>Issuer</th>
    </tr>
"""

for cert in data['results']:
    status_icon = '✅' if cert['status'] == 'pass' else ('⚠️' if cert['status'] == 'warning' else '❌')
    html += f"""
    <tr>
      <td>{cert['host']}</td>
      <td>{status_icon} {cert['status']}</td>
      <td>{cert['days_until_expiry']}</td>
      <td>{cert['issuer']}</td>
    </tr>
    """

html += """
  </table>
</body>
</html>
"""

with open('ssl-report.html', 'w') as f:
    f.write(html)

print("Report generated: ssl-report.html")
```

### 3. Prometheus - Monitoring Integration

**Example: Export metrics**:
```bash
#!/bin/bash
# /usr/local/bin/ssl_exporter.sh

# Get SSL check results
RESULTS=$(reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --format=json)

# Extract metrics
TOTAL=$(echo $RESULTS | jq '.summary.total')
PASSED=$(echo $RESULTS | jq '.summary.passed')
WARNINGS=$(echo $RESULTS | jq '.summary.warnings')
FAILURES=$(echo $RESULTS | jq '.summary.failures')

# Export Prometheus metrics
cat <<EOF > /var/lib/node_exporter/ssl_certificates.prom
# HELP ssl_certificates_total Total SSL certificates
ssl_certificates_total $TOTAL

# HELP ssl_certificates_passed Healthy SSL certificates
ssl_certificates_passed $PASSED

# HELP ssl_certificates_warnings SSL certificates with warnings
ssl_certificates_warnings $WARNINGS

# HELP ssl_certificates_failures SSL certificates with failures
ssl_certificates_failures $FAILURES
EOF
```

### 4. Slack - Alert Integration

**Example: Send Slack notifications**:
```bash
#!/bin/bash
# /etc/cron.daily/ssl-check-slack

WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Check certificates
RESULTS=$(reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --only-failures --format=json)

FAILURES=$(echo $RESULTS | jq '.summary.failures')
WARNINGS=$(echo $RESULTS | jq '.summary.warnings')

if [ "$FAILURES" -gt 0 ] || [ "$WARNINGS" -gt 0 ]; then
  # Build message
  MESSAGE="SSL Certificate Alert\n\n"
  MESSAGE+="Failures: $FAILURES\n"
  MESSAGE+="Warnings: $WARNINGS\n\n"

  # Add failed domains
  FAILED_DOMAINS=$(echo $RESULTS | jq -r '.results[] | "\(.host): \(.days_until_expiry) days remaining"')
  MESSAGE+="$FAILED_DOMAINS"

  # Send to Slack
  curl -X POST "$WEBHOOK_URL" \
    -H 'Content-Type: application/json' \
    -d "{\"text\": \"$MESSAGE\"}"
fi
```

### 5. Grafana - Dashboard Visualization

**Example: InfluxDB data collector**:
```bash
#!/bin/bash
# /etc/cron.hourly/ssl-metrics

# Get SSL check results
RESULTS=$(reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --format=json)

TIMESTAMP=$(date +%s)
TOTAL=$(echo $RESULTS | jq '.summary.total')
PASSED=$(echo $RESULTS | jq '.summary.passed')
WARNINGS=$(echo $RESULTS | jq '.summary.warnings')
FAILURES=$(echo $RESULTS | jq '.summary.failures')

# Write to InfluxDB
curl -XPOST "http://localhost:8086/write?db=monitoring" \
  --data-binary "ssl_certificates,host=nginx total=$TOTAL,passed=$PASSED,warnings=$WARNINGS,failures=$FAILURES $TIMESTAMP"
```

---

## Security Considerations

### 1. Certificate Verification Disabled During Fetch

**Why**: SSL adapter connects with verification disabled to fetch certificate details.

**Risk**: Could potentially connect to malicious server.

**Mitigation**:
- Verification performed separately after fetch
- Results include verification status
- Hostname match checked independently

**Best practice**: Always run with `--check` to see verification results.

### 2. No Certificate Pinning

**Limitation**: SSL adapter does NOT perform certificate pinning.

**Implication**: Cannot detect certificate replacement attacks.

**Use case**: For pinning, use application-level implementation.

### 3. Trust Store Dependency

**Behavior**: Chain validation uses system trust store (`/etc/ssl/certs`, etc.).

**Implication**: Results depend on system's trusted CAs.

**Consideration**: Ensure system trust store is up-to-date.

---

## Performance & Best Practices

### Performance Tips

**1. Use batch mode for multiple domains**:
```bash
# ❌ Slow: Multiple invocations
reveal ssl://example.com --check
reveal ssl://google.com --check
# ...

# ✅ Fast: Single batch invocation
cat domains.txt | reveal --stdin --check
```

**2. Use --summary for large batches**:
```bash
# ❌ Verbose output (100+ domains)
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check

# ✅ Concise summary
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --summary
```

**3. Filter early with --only-failures**:
```bash
# ❌ Shows all results (noisy)
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check

# ✅ Shows only problems
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --only-failures
```

### Best Practices

**1. Monitor regularly**:
- Daily cron job: Check for expiring certificates
- Threshold: Warn at 30 days, critical at 7 days
- Alert: Slack/email notifications for failures

**2. Use CI/CD validation**:
- Pre-deployment: Validate SSL configuration
- Post-deployment: Verify certificates accessible
- Continuous: Daily SSL health checks

**3. Document certificate inventory**:
- Track all domains with SSL certificates
- Document renewal procedures
- Maintain certificate metadata (issuer, expiry, purpose)

**4. Automate renewals**:
- Use Let's Encrypt with auto-renewal
- Validate after renewal with `--check`
- Alert on renewal failures

**5. Progressive investigation**:
- Start with overview (`ssl://example.com`)
- Drill down to elements (`/san`, `/chain`) if needed
- Run health checks (`--check --advanced`) when issues found

---

## Limitations

### 1. No OCSP/Revocation Checking

**Limitation**: SSL adapter does NOT check certificate revocation status (OCSP, CRL).

**Workaround**: Use `openssl s_client -status` for OCSP checking.

### 2. Chain Limited Without PyOpenSSL

**Limitation**: Full chain inspection requires PyOpenSSL (optional dependency).

**Impact**: Basic adapter shows leaf certificate only.

**Workaround**: Install PyOpenSSL: `pip install pyopenssl`

### 3. No Certificate Generation/Modification

**Limitation**: Read-only adapter, cannot create or modify certificates.

**Workaround**: Use OpenSSL tools (`openssl req`, `openssl x509`).

### 4. Timeout on Slow Servers

**Limitation**: Default 10-second connection timeout.

**Impact**: May fail on slow/distant servers.

**Workaround**: Not currently configurable (use openssl s_client with custom timeout).

### 5. No SNI Override

**Limitation**: Uses hostname as SNI value (cannot override).

**Impact**: Cannot test certificates with different SNI values.

**Workaround**: Use `openssl s_client -servername` for custom SNI.

---

## Troubleshooting

### Issue 1: Connection Failed

**Symptom**:
```bash
reveal ssl://example.com
# Error: Connection failed
```

**Causes**:
- Firewall blocking port 443
- Server not responding
- DNS resolution failure

**Solutions**:
```bash
# Check DNS
nslookup example.com

# Check connectivity
telnet example.com 443

# Check firewall
curl -v https://example.com
```

### Issue 2: Chain Validation Failed

**Symptom**:
```bash
reveal ssl://example.com --check
# ❌ Certificate chain validation failed
```

**Causes**:
- Missing intermediate certificate
- Self-signed certificate
- Untrusted CA

**Solutions**:
```bash
# Inspect chain
reveal ssl://example.com/chain

# Check issuer
reveal ssl://example.com/issuer

# Verify intermediate cert installed on server
openssl s_client -connect example.com:443 -showcerts
```

### Issue 3: Hostname Mismatch

**Symptom**:
```bash
reveal ssl://subdomain.example.com --check
# ❌ Hostname does not match certificate
```

**Cause**: Certificate SAN doesn't include subdomain

**Solution**:
```bash
# Check SANs
reveal ssl://subdomain.example.com/san

# Verify expected domain is present
# If missing, obtain new certificate with correct SANs
```

### Issue 4: Batch Check Returns No Results

**Symptom**:
```bash
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check
# No domains found
```

**Causes**:
- Incorrect path pattern
- Nginx config has no SSL servers
- Glob pattern not matching files

**Solutions**:
```bash
# Verify files exist
ls /etc/nginx/conf.d/*.conf

# Check nginx config
reveal /etc/nginx/conf.d/site.conf

# Use absolute path
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check
```

---

## Tips & Tricks

### Tip 1: Quick Multi-Domain Check

```bash
# Check multiple specific domains
echo -e "ssl://example.com\nssl://google.com\nssl://github.com" | \
  reveal --stdin --check --summary
```

### Tip 2: Find Expiring Certificates

```bash
# Find certificates expiring within 30 days
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --format=json | \
  jq '.results[] | select(.days_until_expiry < 30)'
```

### Tip 3: Compare Certificates Across Environments

```bash
# Production
ssh prod-server "reveal ssl://example.com --format=json" > prod-cert.json

# Staging
ssh staging-server "reveal ssl://example.com --format=json" > staging-cert.json

# Compare
jq -s '.[0].common_name as $prod | .[1].common_name as $staging |
  {prod: $prod, staging: $staging, match: ($prod == $staging)}' \
  prod-cert.json staging-cert.json
```

### Tip 4: Generate Renewal Calendar

```bash
# Generate certificate renewal calendar
reveal ssl://nginx:///etc/nginx/conf.d/*.conf --check --format=json | \
  jq -r '.results[] | "\(.valid_until)\t\(.host)\t\(.days_until_expiry) days"' | \
  sort > renewal-calendar.txt
```

### Tip 5: Check Certificate After Renewal

```bash
# Verify certificate renewed successfully
OLD_EXPIRY=$(reveal ssl://example.com/dates --format=json | jq -r '.not_after')
echo "Old expiry: $OLD_EXPIRY"

# ... perform renewal ...

NEW_EXPIRY=$(reveal ssl://example.com/dates --format=json | jq -r '.not_after')
echo "New expiry: $NEW_EXPIRY"

if [ "$OLD_EXPIRY" != "$NEW_EXPIRY" ]; then
  echo "✅ Certificate renewed successfully"
else
  echo "❌ Certificate not renewed"
fi
```

---

## Related Documentation

### Reveal Adapters
- **[Stats Adapter Guide](STATS_ADAPTER_GUIDE.md)** - Codebase metrics and quality
- **[Env Adapter Guide](ENV_ADAPTER_GUIDE.md)** - Environment variable inspection
- **[MySQL Adapter Guide](MYSQL_ADAPTER_GUIDE.md)** - Database health monitoring
- **[Git Adapter Guide](GIT_ADAPTER_GUIDE.md)** - Repository inspection

### Reveal Core
- **[Quick Start](QUICK_START.md)** - Getting started with reveal
- **[Progressive Disclosure Guide](PROGRESSIVE_DISCLOSURE.md)** - Token optimization patterns
- **[Batch Processing Guide](BATCH_PROCESSING.md)** - Batch mode usage
- **[Output Contract](OUTPUT_CONTRACT.md)** - Result structure standards

---

## FAQ

### Q1: Why doesn't ssl:// check certificate revocation?

**A**: OCSP/CRL checking requires external service queries and adds latency. Use `openssl s_client -status` for OCSP checking if needed.

### Q2: Can I check certificates from a load balancer?

**A**: Yes, just use the load balancer's hostname/IP:
```bash
reveal ssl://loadbalancer.example.com
```

### Q3: How do I check certificates for multiple subdomains?

**A**: Create a list and use batch mode:
```bash
cat > domains.txt <<EOF
ssl://api.example.com
ssl://www.example.com
ssl://staging.example.com
EOF

reveal --stdin --check < domains.txt
```

### Q4: Why does health check pass but browser shows warning?

**A**: Possible reasons:
- **Browser uses stricter validation** (e.g., CT log requirements)
- **Client-side certificate pinning** (browser has different pinned cert)
- **HSTS violations** (browser cached previous connection)

Try `--check --advanced` for more details.

### Q5: Can I use ssl:// adapter for internal certificates?

**A**: Yes, but chain validation may fail if using internal CA:
```bash
# Check will fail validation
reveal ssl://internal.example.com --check

# But you can still inspect certificate
reveal ssl://internal.example.com
reveal ssl://internal.example.com/san
```

### Q6: How do I automate certificate renewal notifications?

**A**: See [Workflow 1: Monitor Certificate Expiry](#workflow-1-monitor-certificate-expiry) for cron job example.

### Q7: Can I check certificates on non-standard ports?

**A**: Yes:
```bash
reveal ssl://example.com:8443
```

### Q8: Why is batch mode faster than individual checks?

**A**: Batch mode:
- Single process initialization
- Aggregated output
- Parallel connection handling (future enhancement)

### Q9: How do I validate wildcard certificate coverage?

**A**: Check SANs for wildcard entry:
```bash
reveal ssl://example.com/san --format=json | jq '.wildcard_entries'
```

### Q10: Can ssl:// adapter export metrics to monitoring systems?

**A**: Yes, see [Integration Examples](#integration-examples) for Prometheus, Grafana, and InfluxDB examples.

---

## Version History

### Version 1.0.0 (2025-02-14)
- ✅ Comprehensive SSL adapter documentation
- ✅ Progressive disclosure pattern explained
- ✅ Health check system detailed (basic + advanced)
- ✅ Batch processing modes (nginx, stdin, composable)
- ✅ 6 detailed workflows (monitoring, debugging, validation, audit, CI/CD, renewals)
- ✅ 5 integration examples (jq, Python, Prometheus, Slack, Grafana)
- ✅ Security considerations documented
- ✅ 10 FAQ entries

### Related Documentation
- Based on `adapters/ssl/adapter.py` (current version)
- Based on `adapters/help_data/ssl.yaml` (current version)
- Consolidates 111 references across 10 documentation files

---

**End of SSL Adapter Guide**
