# Domain Adapter Guide (domain://)

**Last Updated**: 2026-02-14
**Version**: 1.0
**Adapter Version**: reveal 0.1.0+

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Core Features](#core-features)
4. [Elements Reference](#elements-reference)
5. [CLI Flags](#cli-flags)
6. [Progressive Disclosure Pattern](#progressive-disclosure-pattern)
7. [Health Check System](#health-check-system)
8. [DNS Validation](#dns-validation)
9. [Cross-Adapter Integration](#cross-adapter-integration)
10. [Detailed Workflows](#detailed-workflows)
11. [Performance Considerations](#performance-considerations)
12. [Limitations](#limitations)
13. [Error Messages](#error-messages)
14. [Tips & Best Practices](#tips-best-practices)
15. [Integration Examples](#integration-examples)
16. [Related Documentation](#related-documentation)
17. [FAQ](#faq)

---

## Overview

The **domain://** adapter provides comprehensive domain infrastructure inspection, including DNS records, SSL certificates, domain health validation, and registrar information. It's designed for DevOps, SRE teams, and anyone managing domain infrastructure.

**Primary Use Cases**:
- Domain health monitoring and validation
- DNS troubleshooting and propagation verification
- Domain migration validation
- Infrastructure auditing
- SSL certificate monitoring (integrated with ssl:// adapter)
- DNS record inspection and analysis

**Key Capabilities**:
- DNS record inspection (A, AAAA, MX, TXT, NS, CNAME, SOA)
- DNS propagation validation across nameservers
- SSL certificate status checking (delegates to ssl:// adapter)
- Domain health checks with actionable remediation
- Registrar and nameserver information
- Progressive disclosure (overview → elements → health checks)
- Cross-adapter integration (seamless ssl:// delegation)

**Design Philosophy**:
- **Token-efficient**: Progressive disclosure prevents overwhelming AI agents
- **Actionable**: Every check includes next steps and remediation guidance
- **Cross-functional**: Integrates DNS + SSL for complete domain health
- **Zero config**: Works without configuration files
- **Composable**: Integrates with jq, monitoring tools, CI/CD pipelines

---

## Quick Start

### 1. Domain Overview

Get high-level domain status (DNS summary, SSL health, nameservers):

```bash
reveal domain://example.com
```

**Returns**: Domain overview with DNS summary, SSL status, nameservers, next steps

### 2. DNS Records

Get all DNS records (A, AAAA, MX, TXT, NS, CNAME, SOA):

```bash
reveal domain://example.com/dns
```

**Returns**: Complete DNS record set for the domain

### 3. SSL Certificate Status

Check SSL certificate health:

```bash
reveal domain://example.com/ssl
```

**Returns**: SSL certificate status (delegates to ssl:// adapter)

### 4. Domain Health Check

Run comprehensive health validation:

```bash
reveal domain://example.com --check
```

**Returns**: DNS resolution check, nameserver response, propagation validation, SSL certificate expiry

### 5. Registrar Information

Get nameserver and registrar info:

```bash
reveal domain://example.com/registrar
```

**Returns**: Nameservers and registrar details (full WHOIS not yet implemented)

### 6. Advanced Health Check

Run deep health validation with advanced SSL checks:

```bash
reveal domain://example.com --check --advanced
```

**Returns**: All basic checks + advanced SSL validation

### 7. Show Only Problems

Filter to show only warnings and failures:

```bash
reveal domain://example.com --check --only-failures
```

**Returns**: Only checks with issues (warnings/failures)

### 8. Batch Domain Checks

Check multiple domains in parallel:

```bash
echo -e "domain://example.com\ndomain://google.com" | reveal --stdin --batch --check
```

**Returns**: Aggregated health check results for all domains

---

## Core Features

### 1. Progressive Disclosure

Start with overview, drill down as needed:

```bash
# Step 1: Overview (token-efficient)
reveal domain://example.com

# Step 2: Deep dive into DNS
reveal domain://example.com/dns

# Step 3: Validate health
reveal domain://example.com --check

# Step 4: Check SSL details
reveal ssl://example.com --check
```

**Why**: Prevents token waste, provides exactly the detail level needed

### 2. DNS Record Inspection

Complete DNS record support:

| Record Type | Description | Use Case |
|-------------|-------------|----------|
| **A** | IPv4 address | Website hosting, API endpoints |
| **AAAA** | IPv6 address | Modern network infrastructure |
| **MX** | Mail exchange | Email routing, spam analysis |
| **TXT** | Text records | SPF, DKIM, domain verification |
| **NS** | Nameservers | DNS delegation, propagation checks |
| **CNAME** | Canonical name | Alias resolution, CDN validation |
| **SOA** | Start of authority | Zone configuration, serial numbers |

**Example**: Extract specific record types with jq:

```bash
reveal domain://example.com/dns --format json | jq '.records.MX'
```

### 3. DNS Propagation Validation

Verify DNS changes have propagated across all nameservers:

```bash
reveal domain://example.com --check
```

**How it works**:
1. Query all authoritative nameservers for the domain
2. Validate consistent responses across nameservers
3. Check for resolution issues
4. Detect propagation delays

**Exit codes**:
- `0` = All checks passed
- `1` = Warnings (e.g., slow propagation)
- `2` = Failures (e.g., resolution errors, SSL expired)

### 4. Health Check System

Comprehensive domain health validation:

**Checks performed**:
- **DNS resolution**: Can the domain be resolved?
- **Nameserver response**: Are nameservers responding?
- **DNS propagation**: Are records consistent across nameservers?
- **SSL certificate**: Is certificate valid and not expiring soon?

**Check statuses**:
- **pass**: Check succeeded, no issues
- **warning**: Non-critical issue (e.g., SSL expires in 20 days)
- **failure**: Critical issue (e.g., domain doesn't resolve, SSL expired)

**Example output structure**:
```json
{
  "type": "domain_health_check",
  "domain": "example.com",
  "status": "warning",
  "checks": [
    {
      "name": "dns_resolution",
      "status": "pass",
      "value": "Resolved",
      "message": "Domain resolves to 93.184.216.34"
    },
    {
      "name": "ssl_certificate",
      "status": "warning",
      "value": "28 days",
      "threshold": "30+ days",
      "message": "SSL certificate expires in 28 days"
    }
  ],
  "summary": {
    "pass": 3,
    "warning": 1,
    "failure": 0
  },
  "next_steps": [
    "Renew SSL certificate: reveal ssl://example.com --check --advanced",
    "View full DNS records: reveal domain://example.com/dns"
  ],
  "exit_code": 1
}
```

### 5. Cross-Adapter Integration

Seamless integration with ssl:// adapter:

```bash
# Domain overview includes SSL summary
reveal domain://example.com

# SSL element delegates to ssl:// adapter
reveal domain://example.com/ssl

# For deep SSL inspection, use ssl:// directly
reveal ssl://example.com --check --advanced
```

**Why delegation matters**:
- domain:// provides SSL overview in context
- ssl:// provides deep certificate inspection
- Avoid feature duplication
- Clear adapter responsibilities

### 6. Actionable Next Steps

Every response includes contextual next steps:

**Example**: After domain overview:
```
Next steps:
- Full health check: reveal domain://example.com --check
- View all DNS records: reveal domain://example.com/dns
- Check SSL certificate: reveal ssl://example.com --check
```

**Example**: After health check with SSL warning:
```
Next steps:
- Renew SSL certificate: reveal ssl://example.com --check --advanced
- View certificate chain: reveal ssl://example.com/chain
- Monitor expiry: reveal ssl://example.com --check >> monitoring.log
```

---

## Elements Reference

The domain:// adapter supports four elements for progressive disclosure:

### 1. dns

**Description**: All DNS records (A, AAAA, MX, TXT, NS, CNAME, SOA)

**Syntax**:
```bash
reveal domain://<domain>/dns
```

**Example**:
```bash
reveal domain://google.com/dns
```

**Output**:
```json
{
  "type": "domain_dns_records",
  "domain": "google.com",
  "records": {
    "A": ["142.250.185.46"],
    "AAAA": ["2607:f8b0:4004:c07::71"],
    "MX": ["smtp.google.com"],
    "TXT": ["v=spf1 include:_spf.google.com ~all"],
    "NS": ["ns1.google.com", "ns2.google.com"],
    "CNAME": [],
    "SOA": ["ns1.google.com"]
  },
  "next_steps": [
    "Check DNS propagation: reveal domain://google.com --check",
    "View SSL certificate: reveal ssl://google.com"
  ]
}
```

**Use when**: Need complete DNS record set for analysis, migration, or troubleshooting

---

### 2. whois

**Description**: WHOIS registration data (registrar, expiry, nameservers)

**Syntax**:
```bash
reveal domain://<domain>/whois
```

**Example**:
```bash
reveal domain://example.com/whois
```

**Status**: ⚠️ **Not yet implemented** - requires python-whois package

**Output**:
```json
{
  "type": "domain_whois",
  "domain": "example.com",
  "error": "WHOIS lookup not yet implemented (requires python-whois)",
  "next_steps": [
    "Install python-whois: pip install python-whois",
    "View DNS instead: reveal domain://example.com/dns"
  ]
}
```

**Future capabilities** (when implemented):
- Registrar information
- Registration and expiry dates
- Registrant contact details (if public)
- Nameserver delegation
- Domain status codes

---

### 3. ssl

**Description**: SSL certificate status (delegates to ssl:// adapter)

**Syntax**:
```bash
reveal domain://<domain>/ssl
```

**Example**:
```bash
reveal domain://example.com/ssl
```

**Output**:
```json
{
  "type": "domain_ssl_status",
  "domain": "example.com",
  "ssl_check": {
    "status": "pass",
    "certificate": {
      "days_until_expiry": 45,
      "subject": "example.com",
      "issuer": "Let's Encrypt Authority X3"
    }
  },
  "next_steps": [
    "Full SSL details: reveal ssl://example.com",
    "Advanced SSL checks: reveal ssl://example.com --check --advanced"
  ]
}
```

**Use when**: Need SSL status in domain context (for deep SSL inspection, use `ssl://` directly)

**Delegation pattern**:
- `domain://example.com` → SSL summary in overview
- `domain://example.com/ssl` → SSL status check
- `ssl://example.com` → Full certificate details
- `ssl://example.com --check` → Deep SSL validation

---

### 4. registrar

**Description**: Registrar and nameserver information

**Syntax**:
```bash
reveal domain://<domain>/registrar
```

**Example**:
```bash
reveal domain://example.com/registrar
```

**Output**:
```json
{
  "type": "domain_registrar",
  "domain": "example.com",
  "nameservers": [
    "a.iana-servers.net",
    "b.iana-servers.net"
  ],
  "note": "Full registrar info requires WHOIS lookup (not yet implemented)",
  "next_steps": [
    "View DNS records: reveal domain://example.com/dns"
  ]
}
```

**Use when**: Need nameserver information for DNS troubleshooting or migration

---

## CLI Flags

### --check

**Description**: Run domain health checks (DNS resolution, propagation, SSL certificate)

**Syntax**:
```bash
reveal domain://<domain> --check
```

**Example**:
```bash
reveal domain://example.com --check
```

**Checks performed**:
1. **DNS resolution**: Can the domain be resolved to IP addresses?
2. **Nameserver response**: Are authoritative nameservers responding?
3. **DNS propagation**: Are DNS records consistent across all nameservers?
4. **SSL certificate**: Is the certificate valid and not expiring soon?

**Exit codes**:
- `0` = All checks passed (status: pass)
- `1` = Some checks have warnings (status: warning)
- `2` = Some checks failed (status: failure)

**Use in automation**:
```bash
# CI/CD validation
if reveal domain://staging.example.com --check --format json > /dev/null; then
  echo "Domain health: OK"
else
  echo "Domain health: FAILED (exit code: $?)"
  exit 1
fi
```

---

### --advanced

**Description**: Run advanced checks (use with --check for deeper validation)

**Syntax**:
```bash
reveal domain://<domain> --check --advanced
```

**Example**:
```bash
reveal domain://example.com --check --advanced
```

**Additional checks** (when combined with --check):
- Advanced SSL validation (certificate chain, validity, trust)
- Deep DNS diagnostics
- Extended propagation validation

**Performance note**: Advanced checks take 2-3x longer (requires more SSL validation)

---

### --only-failures

**Description**: Hide healthy results, show only warnings and failures

**Syntax**:
```bash
reveal domain://<domain> --check --only-failures
```

**Example**:
```bash
reveal domain://example.com --check --only-failures
```

**Use cases**:
- Production monitoring (focus on problems)
- Log analysis (reduce noise)
- Alerting systems (only show issues)

**Example output** (when all checks pass):
```json
{
  "type": "domain_health_check",
  "domain": "example.com",
  "status": "pass",
  "checks": [],
  "summary": {"pass": 4, "warning": 0, "failure": 0},
  "next_steps": []
}
```

**Example output** (when SSL expiring):
```json
{
  "type": "domain_health_check",
  "domain": "example.com",
  "status": "warning",
  "checks": [
    {
      "name": "ssl_certificate",
      "status": "warning",
      "value": "15 days",
      "threshold": "30+ days",
      "message": "SSL certificate expires in 15 days"
    }
  ],
  "summary": {"pass": 3, "warning": 1, "failure": 0},
  "next_steps": ["Renew SSL certificate"]
}
```

---

### --batch

**Description**: Batch mode with aggregated results (use with --stdin)

**Syntax**:
```bash
<domains> | reveal --stdin --batch --check
```

**Example**:
```bash
echo -e "domain://example.com\ndomain://google.com\ndomain://github.com" | \
  reveal --stdin --batch --check
```

**Output structure**:
```json
{
  "type": "batch_results",
  "total": 3,
  "successful": 2,
  "failed": 1,
  "results": [
    {"domain": "example.com", "status": "pass"},
    {"domain": "google.com", "status": "pass"},
    {"domain": "github.com", "status": "warning", "issues": ["SSL expiring"]}
  ]
}
```

**Use cases**:
- Monitor multiple domains in parallel
- Infrastructure audits
- Compliance validation
- Migration verification

---

## Progressive Disclosure Pattern

The domain:// adapter uses **progressive disclosure** to provide exactly the level of detail needed, preventing token waste in AI-assisted workflows.

### Level 1: Overview (Token-Efficient)

**Command**:
```bash
reveal domain://example.com
```

**Token cost**: ~200-400 tokens

**Returns**:
- Domain name
- DNS summary (nameservers, A records, MX status)
- SSL summary (certificate status, expiry)
- Next steps

**Use when**: Initial domain assessment, quick status check

---

### Level 2: Element Details (Moderate Detail)

**Command**:
```bash
reveal domain://example.com/dns
reveal domain://example.com/ssl
reveal domain://example.com/registrar
```

**Token cost**: ~400-800 tokens per element

**Returns**: Complete data for requested element (all DNS records, SSL certificate details, registrar info)

**Use when**: Need specific domain aspect details

---

### Level 3: Health Checks (Comprehensive Validation)

**Command**:
```bash
reveal domain://example.com --check
reveal domain://example.com --check --advanced
```

**Token cost**: ~600-1200 tokens

**Returns**:
- All health check results
- Check statuses (pass/warning/failure)
- Summary metrics
- Actionable next steps
- Exit code for automation

**Use when**: Domain validation, migration verification, production readiness

---

### Level 4: Deep Inspection (Cross-Adapter)

**Command**:
```bash
reveal ssl://example.com --check --advanced
reveal ssl://example.com/chain
reveal ssl://example.com --check-revocation
```

**Token cost**: ~800-2000 tokens

**Returns**: Deep SSL certificate inspection (use ssl:// adapter directly)

**Use when**: SSL troubleshooting, security audits, certificate chain issues

---

### Pattern Summary

```
Overview (200 tokens)
   ↓
Element details (400 tokens)
   ↓
Health checks (600 tokens)
   ↓
Deep inspection (1000+ tokens)
```

**Rule**: Start shallow, drill down only when needed

---

## Health Check System

### Overview

Health checks validate domain infrastructure across DNS, propagation, and SSL:

```bash
reveal domain://example.com --check
```

**Exit codes**:
- `0` = Pass (all checks healthy)
- `1` = Warning (non-critical issues)
- `2` = Failure (critical issues)

---

### Check Types

#### 1. DNS Resolution Check

**What it validates**: Domain resolves to IP addresses

**Pass criteria**: Domain resolves to at least one A or AAAA record

**Failure scenarios**:
- Domain doesn't resolve (NXDOMAIN)
- DNS timeout
- No A/AAAA records found

**Example result**:
```json
{
  "name": "dns_resolution",
  "status": "pass",
  "value": "Resolved",
  "threshold": "Resolves to IPs",
  "message": "Domain resolves to 93.184.216.34",
  "severity": "high"
}
```

---

#### 2. Nameserver Response Check

**What it validates**: Authoritative nameservers are responding

**Pass criteria**: At least one nameserver responds successfully

**Failure scenarios**:
- All nameservers timeout
- No authoritative nameservers found
- Nameserver configuration errors

**Example result**:
```json
{
  "name": "nameserver_response",
  "status": "pass",
  "value": "2/2 responding",
  "threshold": "At least 1 responds",
  "message": "All nameservers responding normally",
  "severity": "high"
}
```

---

#### 3. DNS Propagation Check

**What it validates**: DNS records are consistent across all nameservers

**Pass criteria**: All nameservers return consistent DNS records

**Warning scenarios**:
- Inconsistent records across nameservers (propagation in progress)
- Some nameservers slow to respond

**Failure scenarios**:
- Complete propagation failure
- Conflicting records across nameservers

**Example result**:
```json
{
  "name": "dns_propagation",
  "status": "warning",
  "value": "Propagating",
  "threshold": "Consistent records",
  "message": "DNS records propagating (1/2 nameservers updated)",
  "severity": "medium"
}
```

**Performance note**: Propagation check queries all authoritative nameservers (slower than basic checks)

---

#### 4. SSL Certificate Check

**What it validates**: SSL certificate is valid and not expiring soon

**Pass criteria**: Certificate valid for 30+ days

**Warning criteria**: Certificate expires in 7-30 days

**Failure scenarios**:
- Certificate already expired
- Certificate expires in <7 days
- No valid certificate found
- Certificate validation failed

**Example result**:
```json
{
  "name": "ssl_certificate",
  "status": "warning",
  "value": "15 days",
  "threshold": "30+ days",
  "message": "SSL certificate expires in 15 days",
  "severity": "high"
}
```

---

### Check Status Interpretation

| Status | Meaning | Action Required | Exit Code |
|--------|---------|-----------------|-----------|
| **pass** | Check succeeded, no issues | None | 0 |
| **warning** | Non-critical issue detected | Monitor, plan remediation | 1 |
| **failure** | Critical issue, immediate action needed | Fix immediately | 2 |

---

### Check Summary

Health check results include summary metrics:

```json
{
  "summary": {
    "pass": 3,
    "warning": 1,
    "failure": 0
  }
}
```

**Overall status calculation**:
- If any check failed → overall status: **failure**
- Else if any check has warning → overall status: **warning**
- Else → overall status: **pass**

---

### Actionable Next Steps

Every health check includes contextual next steps based on results:

**Example** (SSL expiring soon):
```
Next steps:
- Renew SSL certificate: reveal ssl://example.com --check --advanced
- View certificate details: reveal ssl://example.com/full
- Check certificate chain: reveal ssl://example.com/chain
```

**Example** (DNS propagation issue):
```
Next steps:
- View current DNS records: reveal domain://example.com/dns
- Check specific nameserver: dig @ns1.example.com example.com
- Wait for propagation and re-check: reveal domain://example.com --check
```

---

## DNS Validation

### DNS Record Types

Complete DNS record support via dnspython:

| Record Type | Description | Validation |
|-------------|-------------|------------|
| **A** | IPv4 address | Validates resolution to IPv4 |
| **AAAA** | IPv6 address | Validates IPv6 support |
| **MX** | Mail exchange | Checks email server configuration |
| **TXT** | Text records | Validates SPF, DKIM, domain verification |
| **NS** | Nameservers | Identifies authoritative nameservers |
| **CNAME** | Canonical name | Checks alias configuration |
| **SOA** | Start of authority | Validates zone configuration |

---

### DNS Propagation Validation

**How propagation checking works**:

1. Query NS records to find all authoritative nameservers
2. Query each nameserver for domain's A records
3. Compare responses across all nameservers
4. Detect inconsistencies (propagation in progress)
5. Report propagation status

**Example scenario**: Domain migration

```bash
# Before migration: Old IP
reveal domain://example.com --check
# Status: pass, IP: 1.2.3.4

# During migration: Some nameservers updated
reveal domain://example.com --check
# Status: warning, message: "DNS propagating (1/2 nameservers updated)"

# After migration: All nameservers updated
reveal domain://example.com --check
# Status: pass, IP: 5.6.7.8
```

---

### DNS Troubleshooting

**Common DNS issues and solutions**:

#### Issue: Domain doesn't resolve

```bash
reveal domain://example.com --check
# Status: failure, message: "Domain does not resolve (NXDOMAIN)"
```

**Diagnosis**:
```bash
reveal domain://example.com/dns
# Check if A/AAAA records exist

reveal domain://example.com/registrar
# Check nameserver configuration
```

**Solutions**:
- Verify domain registration is active
- Check nameserver configuration at registrar
- Verify DNS records are configured correctly

---

#### Issue: Nameservers not responding

```bash
reveal domain://example.com --check
# Status: failure, message: "Nameservers not responding"
```

**Diagnosis**:
```bash
reveal domain://example.com/registrar
# Check which nameservers are configured

dig @ns1.example.com example.com
# Test each nameserver directly
```

**Solutions**:
- Verify nameserver hostnames are correct
- Check nameserver availability
- Contact DNS provider

---

#### Issue: DNS propagation delays

```bash
reveal domain://example.com --check
# Status: warning, message: "DNS records propagating (1/3 nameservers updated)"
```

**Diagnosis**:
```bash
reveal domain://example.com/dns
# Check current records

# Query each nameserver directly
dig @ns1.example.com example.com
dig @ns2.example.com example.com
dig @ns3.example.com example.com
```

**Solutions**:
- Wait for propagation to complete (typically 5-15 minutes)
- Verify all nameservers are accessible
- Re-check after waiting: `reveal domain://example.com --check`

---

## Cross-Adapter Integration

### SSL Delegation Pattern

The domain:// adapter integrates seamlessly with ssl:// for certificate inspection:

**Integration levels**:

1. **Overview** (domain:// includes SSL summary):
```bash
reveal domain://example.com
# Returns: domain overview + SSL status summary
```

2. **SSL Element** (domain:// delegates to ssl://):
```bash
reveal domain://example.com/ssl
# Returns: SSL check result with next steps to use ssl://
```

3. **Deep SSL** (use ssl:// directly):
```bash
reveal ssl://example.com
reveal ssl://example.com --check
reveal ssl://example.com --check --advanced
```

---

### When to Use Which Adapter

| Need | Use | Example |
|------|-----|---------|
| Domain overview | `domain://` | `reveal domain://example.com` |
| DNS records | `domain://domain/dns` | `reveal domain://example.com/dns` |
| Domain health | `domain:// --check` | `reveal domain://example.com --check` |
| SSL status in context | `domain://domain/ssl` | `reveal domain://example.com/ssl` |
| Deep SSL inspection | `ssl://` | `reveal ssl://example.com` |
| SSL health checks | `ssl:// --check` | `reveal ssl://example.com --check` |
| Certificate chain | `ssl://domain/chain` | `reveal ssl://example.com/chain` |
| Certificate elements | `ssl://domain/san` | `reveal ssl://example.com/san` |

**Rule**: Use domain:// for DNS + domain health, use ssl:// for deep certificate inspection

---

### Combined Workflow Example

Complete domain + SSL audit:

```bash
# Step 1: Domain overview
reveal domain://example.com

# Step 2: Domain health check
reveal domain://example.com --check

# Step 3: Full DNS records
reveal domain://example.com/dns

# Step 4: Deep SSL inspection
reveal ssl://example.com --check --advanced

# Step 5: Certificate chain validation
reveal ssl://example.com/chain

# Step 6: SAN (Subject Alternative Names)
reveal ssl://example.com/san
```

---

## Detailed Workflows

### Workflow 1: Domain Health Check

**Scenario**: Validate domain is correctly configured and healthy

**Steps**:

```bash
# Step 1: Quick overview
reveal domain://example.com
# Returns: DNS summary, SSL status, nameservers

# Step 2: Comprehensive health check
reveal domain://example.com --check
# Validates: DNS resolution, nameserver response, propagation, SSL

# Step 3: Review DNS records (if issues found)
reveal domain://example.com/dns
# Returns: All DNS records (A, AAAA, MX, TXT, NS, CNAME, SOA)

# Step 4: Deep SSL inspection (if SSL issues)
reveal ssl://example.com --check
# Returns: Certificate details, expiry, validation status
```

**Automation example** (CI/CD):
```bash
#!/bin/bash
if ! reveal domain://staging.example.com --check --format json > /dev/null; then
  echo "Domain health check failed (exit code: $?)"
  reveal domain://staging.example.com --check --only-failures
  exit 1
fi
echo "Domain health: OK"
```

---

### Workflow 2: DNS Troubleshooting

**Scenario**: Debug DNS propagation or resolution issues

**Steps**:

```bash
# Step 1: Run health check (includes propagation validation)
reveal domain://example.com --check
# Status: warning, message: "DNS propagating (1/2 nameservers updated)"

# Step 2: View all DNS records
reveal domain://example.com/dns
# Returns: Current A, AAAA, MX, TXT, NS, CNAME, SOA records

# Step 3: Extract specific record types
reveal domain://example.com/dns --format json | jq '.records.A'
# Output: ["93.184.216.34"]

# Step 4: Check nameserver configuration
reveal domain://example.com/registrar
# Returns: Authoritative nameservers

# Step 5: Query nameservers directly (if needed)
dig @ns1.example.com example.com
dig @ns2.example.com example.com
```

**Common diagnoses**:
- **All nameservers return same records** → Propagation complete
- **Nameservers return different records** → Propagation in progress, wait and re-check
- **Some nameservers timeout** → Nameserver availability issue, contact provider

---

### Workflow 3: Domain Migration Validation

**Scenario**: Verify DNS changes have propagated correctly after domain/hosting migration

**Pre-migration**:

```bash
# Document current state
reveal domain://example.com --check > pre-migration.json
reveal domain://example.com/dns >> pre-migration.json
```

**During migration**:

```bash
# Monitor propagation every 5 minutes
watch -n 300 'reveal domain://example.com --check'
```

**Post-migration validation**:

```bash
# Step 1: Verify DNS propagation
reveal domain://example.com --check
# Expected: status=pass, new IP addresses

# Step 2: Verify all DNS records updated
reveal domain://example.com/dns
# Check: A, AAAA, MX, TXT records match new configuration

# Step 3: Verify SSL certificate still valid
reveal ssl://example.com --check
# Expected: status=pass, certificate valid

# Step 4: Compare pre/post migration
diff <(jq -S . pre-migration.json) <(jq -S . post-migration.json)
```

---

### Workflow 4: Domain + SSL Audit

**Scenario**: Comprehensive domain and SSL health check for compliance/security audit

**Steps**:

```bash
# Step 1: Domain health check
reveal domain://example.com --check
# Validates: DNS resolution, nameserver response, propagation, SSL status

# Step 2: Advanced SSL inspection
reveal ssl://example.com --check --advanced
# Validates: Certificate validity, chain, expiry, trust

# Step 3: Full DNS records
reveal domain://example.com/dns
# Returns: All DNS records for audit documentation

# Step 4: Certificate chain validation
reveal ssl://example.com/chain
# Returns: Full certificate chain (leaf → intermediate → root)

# Step 5: SAN validation
reveal ssl://example.com/san
# Returns: All domains covered by certificate
```

**Generate audit report**:

```bash
#!/bin/bash
DOMAIN="example.com"
REPORT="audit-report-$(date +%Y%m%d).json"

{
  echo '{"domain": "'$DOMAIN'", "audit_date": "'$(date -Iseconds)'",'
  echo '"health_check":'
  reveal domain://$DOMAIN --check --format json
  echo ','
  echo '"ssl_check":'
  reveal ssl://$DOMAIN --check --advanced --format json
  echo ','
  echo '"dns_records":'
  reveal domain://$DOMAIN/dns --format json
  echo '}'
} > $REPORT

echo "Audit report saved: $REPORT"
```

---

### Workflow 5: Production Monitoring

**Scenario**: Continuous domain health monitoring for production infrastructure

**Setup monitoring script**:

```bash
#!/bin/bash
# monitor-domains.sh

DOMAINS=(
  "example.com"
  "api.example.com"
  "app.example.com"
)

ALERT_EMAIL="ops@example.com"

for domain in "${DOMAINS[@]}"; do
  if ! reveal domain://$domain --check --only-failures --format json > /dev/null; then
    EXIT_CODE=$?
    MESSAGE=$(reveal domain://$domain --check --only-failures)

    echo "ALERT: Domain health check failed for $domain (exit code: $EXIT_CODE)"
    echo "$MESSAGE"

    # Send alert
    echo "$MESSAGE" | mail -s "Domain Alert: $domain" $ALERT_EMAIL
  fi
done
```

**Cron setup** (check every 15 minutes):
```bash
*/15 * * * * /opt/scripts/monitor-domains.sh >> /var/log/domain-monitor.log 2>&1
```

**Integration with monitoring tools**:

```bash
# Prometheus exporter
reveal domain://example.com --check --format json | jq -r '
  .checks[] |
  "domain_health{domain=\"\(.domain)\",check=\"\(.name)\",status=\"\(.status)\"} \(if .status == "pass" then 1 elif .status == "warning" then 0.5 else 0 end)"
' > /var/lib/prometheus/domain-health.prom
```

---

### Workflow 6: Batch Domain Validation

**Scenario**: Validate health of multiple domains in parallel

**Create domain list**:

```bash
cat > domains.txt <<EOF
example.com
google.com
github.com
stackoverflow.com
EOF
```

**Batch health check**:

```bash
cat domains.txt | sed 's/^/domain:\/\//' | reveal --stdin --batch --check
```

**Filter to only problems**:

```bash
cat domains.txt | sed 's/^/domain:\/\//' | reveal --stdin --batch --check --only-failures
```

**Generate CSV report**:

```bash
#!/bin/bash
echo "Domain,Status,Issues" > report.csv

cat domains.txt | while read domain; do
  RESULT=$(reveal domain://$domain --check --format json)
  STATUS=$(echo "$RESULT" | jq -r '.status')
  ISSUES=$(echo "$RESULT" | jq -r '.checks[] | select(.status != "pass") | .message' | tr '\n' '; ')
  echo "$domain,$STATUS,$ISSUES" >> report.csv
done

echo "Report saved: report.csv"
```

---

## Performance Considerations

### Operation Timing

| Operation | Typical Duration | Notes |
|-----------|-----------------|-------|
| Overview | 0.5-1s | Fast (single DNS query + SSL summary) |
| DNS records | 0.3-0.8s | Fast (single DNS lookup) |
| SSL element | 1-2s | Moderate (SSL handshake required) |
| Health check (basic) | 2-4s | Moderate (multiple DNS + SSL queries) |
| Health check (advanced) | 4-8s | Slower (deep SSL validation) |
| Propagation check | 3-6s | Slower (queries all nameservers) |

---

### Optimization Strategies

#### 1. Progressive Disclosure

Start with cheap operations, drill down only when needed:

```bash
# ❌ Expensive: Always use full health check
reveal domain://example.com --check --advanced

# ✅ Efficient: Start with overview, check only if issues
reveal domain://example.com
# If issues detected, then:
reveal domain://example.com --check
```

**Token savings**: ~70% (200 tokens vs 800 tokens)

---

#### 2. Batch Processing

Check multiple domains in parallel instead of sequentially:

```bash
# ❌ Slow: Sequential checks (10 domains = 30-40 seconds)
for domain in $(cat domains.txt); do
  reveal domain://$domain --check
done

# ✅ Fast: Parallel batch processing (10 domains = 5-8 seconds)
cat domains.txt | sed 's/^/domain:\/\//' | reveal --stdin --batch --check
```

**Performance gain**: 4-5x faster

---

#### 3. Caching Strategy

Cache domain health results when appropriate:

```bash
#!/bin/bash
CACHE_FILE="/tmp/domain-cache-$(date +%Y%m%d-%H).json"
CACHE_TTL=3600  # 1 hour

if [ -f "$CACHE_FILE" ] && [ $(($(date +%s) - $(stat -c %Y "$CACHE_FILE"))) -lt $CACHE_TTL ]; then
  cat "$CACHE_FILE"
else
  reveal domain://example.com --check --format json | tee "$CACHE_FILE"
fi
```

**Use case**: Dashboards, frequent checks, CI/CD pipelines

---

#### 4. Filter Early

Use `--only-failures` to reduce output processing:

```bash
# ❌ Large output: All checks (even passing)
reveal domain://example.com --check | process-results.sh

# ✅ Minimal output: Only problems
reveal domain://example.com --check --only-failures | alert.sh
```

**Benefit**: Reduced output size (especially for monitoring systems)

---

### Parallel Execution

Check multiple domains simultaneously with xargs:

```bash
cat domains.txt | xargs -P 10 -I {} sh -c 'reveal domain://{} --check'
```

**Parameters**:
- `-P 10`: Run 10 parallel processes
- Adjust based on system resources and network bandwidth

---

## Limitations

### Current Limitations

1. **WHOIS not implemented**
   - **Status**: Placeholder only, returns error
   - **Workaround**: Use external `whois` command
   - **Future**: Will require python-whois package

2. **No DNS record modification**
   - **Limitation**: Read-only (inspection only)
   - **Design**: Intentional (inspection tool, not DNS manager)
   - **Workaround**: Use DNS provider's API or control panel

3. **Propagation check performance**
   - **Issue**: Queries all nameservers (3-6 seconds)
   - **Impact**: Slower than basic checks
   - **Workaround**: Use basic overview for quick checks, propagation check only when needed

4. **SSL check delegates to ssl://**
   - **Design**: ssl:// adapter owns certificate inspection
   - **Impact**: domain:// provides SSL summary only
   - **Workaround**: Use ssl:// directly for deep SSL inspection

5. **Requires dnspython**
   - **Dependency**: `pip install dnspython`
   - **Impact**: Won't work without dnspython
   - **Workaround**: Install dependency

6. **No batch mode for elements**
   - **Limitation**: Batch mode only supported for health checks
   - **Impact**: Can't batch `domain://*/dns` queries
   - **Workaround**: Use bash loops with xargs for parallel element queries

---

### Design Limitations (Intentional)

1. **No DNS modification**: Inspection only (by design)
2. **No WHOIS caching**: Fresh queries every time (accuracy over speed)
3. **No custom nameserver queries**: Uses system resolver + authoritative nameservers
4. **SSL delegation required**: Avoids feature duplication with ssl:// adapter

---

## Error Messages

### Common Errors and Solutions

#### Error: "Domain does not resolve (NXDOMAIN)"

**Meaning**: Domain doesn't exist or has no DNS records

**Solutions**:
```bash
# Verify domain registration
whois example.com

# Check nameserver configuration
reveal domain://example.com/registrar

# Verify DNS records are configured
reveal domain://example.com/dns
```

---

#### Error: "Nameservers not responding"

**Meaning**: Authoritative nameservers are unreachable or timing out

**Solutions**:
```bash
# Check which nameservers are configured
reveal domain://example.com/registrar

# Test each nameserver directly
dig @ns1.example.com example.com

# Verify nameserver hostnames are correct at registrar
```

---

#### Error: "DNS records propagating (1/2 nameservers updated)"

**Meaning**: DNS change in progress, not all nameservers updated

**Status**: Warning (not failure)

**Solutions**:
```bash
# Wait 5-15 minutes for propagation
sleep 300

# Re-check propagation status
reveal domain://example.com --check

# Query specific nameserver to verify
dig @ns1.example.com example.com
dig @ns2.example.com example.com
```

---

#### Error: "SSL certificate expired"

**Meaning**: Certificate expired (days_until_expiry < 0)

**Solutions**:
```bash
# Check certificate details
reveal ssl://example.com --check

# View expiry date
reveal ssl://example.com/dates

# Renew certificate (provider-specific)
```

---

#### Error: "WHOIS lookup not yet implemented (requires python-whois)"

**Meaning**: WHOIS feature not yet implemented

**Status**: Feature pending

**Workarounds**:
```bash
# Use external whois command
whois example.com

# Or use online WHOIS lookup services
```

---

#### Error: "ModuleNotFoundError: No module named 'dns'"

**Meaning**: dnspython package not installed

**Solution**:
```bash
pip install dnspython
```

---

## Tips & Best Practices

### 1. Start with Overview, Then Drill Down

```bash
# ❌ Wasteful: Jump to expensive operations
reveal domain://example.com --check --advanced

# ✅ Efficient: Progressive disclosure
reveal domain://example.com              # Overview (200 tokens)
# If issues detected:
reveal domain://example.com --check      # Validation (600 tokens)
# If deeper SSL inspection needed:
reveal ssl://example.com --check --advanced
```

**Token savings**: 50-70% in typical workflows

---

### 2. Use --only-failures in Production

```bash
# ❌ Noisy: All checks (passing + failing)
reveal domain://example.com --check

# ✅ Focused: Only problems
reveal domain://example.com --check --only-failures
```

**Benefit**: Cleaner logs, easier alerting

---

### 3. Combine with ssl:// for Complete Coverage

```bash
# Domain health (DNS + basic SSL)
reveal domain://example.com --check

# Deep SSL inspection
reveal ssl://example.com --check --advanced

# Certificate chain validation
reveal ssl://example.com/chain
```

**Why**: domain:// provides SSL summary, ssl:// provides deep inspection

---

### 4. Use Batch Mode for Multiple Domains

```bash
# ✅ Parallel: Fast batch processing
cat domains.txt | sed 's/^/domain:\/\//' | reveal --stdin --batch --check
```

**Performance**: 4-5x faster than sequential loops

---

### 5. Cache Results When Appropriate

```bash
# Cache for 1 hour (dashboards, frequent checks)
CACHE_FILE="/tmp/domain-cache.json"
if [ ! -f "$CACHE_FILE" ] || [ $(($(date +%s) - $(stat -c %Y "$CACHE_FILE"))) -gt 3600 ]; then
  reveal domain://example.com --check --format json > "$CACHE_FILE"
fi
cat "$CACHE_FILE"
```

**Benefit**: Reduced load on DNS servers, faster dashboards

---

### 6. Monitor Exit Codes in Automation

```bash
if ! reveal domain://example.com --check > /dev/null; then
  EXIT_CODE=$?
  if [ $EXIT_CODE -eq 1 ]; then
    echo "Warning: Non-critical issues detected"
  elif [ $EXIT_CODE -eq 2 ]; then
    echo "Error: Critical issues detected"
    exit 1
  fi
fi
```

**Exit codes**:
- `0` = Pass (all healthy)
- `1` = Warning (non-critical)
- `2` = Failure (critical)

---

### 7. Use jq for Advanced Filtering

```bash
# Extract only failed checks
reveal domain://example.com --check --format json | \
  jq '.checks[] | select(.status == "failure")'

# Get SSL expiry days
reveal domain://example.com --check --format json | \
  jq '.checks[] | select(.name == "ssl_certificate") | .value'

# Count checks by status
reveal domain://example.com --check --format json | \
  jq '.summary'
```

---

### 8. Validate Propagation After DNS Changes

```bash
# After making DNS changes, monitor propagation
watch -n 60 'reveal domain://example.com --check'

# When status changes from "warning" to "pass", propagation complete
```

---

### 9. Document Domain Configuration

```bash
# Generate domain documentation
reveal domain://example.com --format json > docs/domain-config.json
reveal domain://example.com/dns --format json > docs/dns-records.json
reveal ssl://example.com --check --format json > docs/ssl-certificate.json
```

**Use case**: Onboarding, disaster recovery, compliance

---

### 10. Combine with Monitoring Tools

```bash
# Prometheus exporter
reveal domain://example.com --check --format json | jq -r '
  .checks[] |
  "domain_health{domain=\"example.com\",check=\"\(.name)\"} \(if .status == "pass" then 1 else 0 end)"
'

# Grafana alerting
if [ $(reveal domain://example.com --check --format json | jq '.exit_code') -ne 0 ]; then
  curl -X POST https://grafana.example.com/api/alerts \
    -d '{"message": "Domain health check failed"}'
fi
```

---

## Integration Examples

### 1. jq Integration

**Filter to failed checks**:
```bash
reveal domain://example.com --check --format json | \
  jq '.checks[] | select(.status != "pass")'
```

**Extract SSL expiry**:
```bash
reveal domain://example.com --check --format json | \
  jq -r '.checks[] | select(.name == "ssl_certificate") | .value'
```

**Generate summary table**:
```bash
reveal domain://example.com --check --format json | \
  jq -r '.checks[] | [.name, .status, .value] | @tsv'
```

---

### 2. Python Integration

```python
import subprocess
import json

def check_domain_health(domain):
    """Check domain health and return results."""
    result = subprocess.run(
        ['reveal', f'domain://{domain}', '--check', '--format', 'json'],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"Warning: Domain {domain} has issues (exit code: {result.returncode})")

    data = json.loads(result.stdout)
    return data

# Check single domain
health = check_domain_health('example.com')
print(f"Status: {health['status']}")
print(f"Summary: {health['summary']}")

# Check multiple domains
domains = ['example.com', 'google.com', 'github.com']
for domain in domains:
    health = check_domain_health(domain)
    if health['status'] != 'pass':
        print(f"⚠️  {domain}: {health['status']}")
```

---

### 3. Shell Script Integration

**Domain monitoring script**:

```bash
#!/bin/bash
# monitor-domain.sh - Check domain health and alert on failures

DOMAIN="$1"
ALERT_EMAIL="ops@example.com"

if [ -z "$DOMAIN" ]; then
  echo "Usage: $0 <domain>"
  exit 1
fi

RESULT=$(reveal domain://$DOMAIN --check --format json)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  STATUS=$(echo "$RESULT" | jq -r '.status')
  ISSUES=$(echo "$RESULT" | jq -r '.checks[] | select(.status != "pass") | .message')

  echo "ALERT: Domain $DOMAIN has issues (status: $STATUS)"
  echo "$ISSUES"

  # Send email alert
  echo "$ISSUES" | mail -s "Domain Alert: $DOMAIN ($STATUS)" $ALERT_EMAIL

  exit $EXIT_CODE
fi

echo "Domain $DOMAIN: OK"
```

---

### 4. GitHub Actions Integration

```yaml
name: Domain Health Check

on:
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours
  workflow_dispatch:

jobs:
  check-domains:
    runs-on: ubuntu-latest
    steps:
      - name: Install reveal
        run: pip install reveal-tool

      - name: Install dnspython
        run: pip install dnspython

      - name: Check production domain
        run: |
          reveal domain://example.com --check
          EXIT_CODE=$?
          if [ $EXIT_CODE -ne 0 ]; then
            echo "::error::Domain health check failed (exit code: $EXIT_CODE)"
            exit $EXIT_CODE
          fi

      - name: Check staging domain
        run: |
          reveal domain://staging.example.com --check

      - name: Generate report
        if: always()
        run: |
          reveal domain://example.com --check --format json > domain-health.json

      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v3
        with:
          name: domain-health-report
          path: domain-health.json
```

---

### 5. Prometheus Exporter

```bash
#!/bin/bash
# domain-exporter.sh - Export domain health metrics for Prometheus

DOMAINS=("example.com" "api.example.com" "app.example.com")
OUTPUT_FILE="/var/lib/prometheus/domain-health.prom"

> $OUTPUT_FILE

for domain in "${DOMAINS[@]}"; do
  RESULT=$(reveal domain://$domain --check --format json)

  # Overall health (1=pass, 0.5=warning, 0=failure)
  STATUS=$(echo "$RESULT" | jq -r '.status')
  if [ "$STATUS" == "pass" ]; then
    HEALTH=1
  elif [ "$STATUS" == "warning" ]; then
    HEALTH=0.5
  else
    HEALTH=0
  fi

  echo "domain_health{domain=\"$domain\"} $HEALTH" >> $OUTPUT_FILE

  # Individual checks
  echo "$RESULT" | jq -r --arg domain "$domain" '
    .checks[] |
    "domain_check{domain=\"\($domain)\",check=\"\(.name)\",status=\"\(.status)\"} \(if .status == "pass" then 1 elif .status == "warning" then 0.5 else 0 end)"
  ' >> $OUTPUT_FILE

  # SSL expiry days
  SSL_DAYS=$(echo "$RESULT" | jq -r '.checks[] | select(.name == "ssl_certificate") | .value | match("[0-9]+") | .string')
  if [ -n "$SSL_DAYS" ]; then
    echo "domain_ssl_expiry_days{domain=\"$domain\"} $SSL_DAYS" >> $OUTPUT_FILE
  fi
done

echo "Metrics exported to $OUTPUT_FILE"
```

---

### 6. Grafana Dashboard Query

```promql
# Domain health status (1=pass, 0.5=warning, 0=failure)
domain_health{domain="example.com"}

# Alert when health drops below 1
domain_health < 1

# SSL certificate expiry days
domain_ssl_expiry_days{domain="example.com"}

# Alert when SSL expires in <30 days
domain_ssl_expiry_days < 30
```

---

### 7. Slack Alerting

```bash
#!/bin/bash
# slack-alert.sh - Send domain health alerts to Slack

DOMAIN="$1"
WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

RESULT=$(reveal domain://$DOMAIN --check --format json)
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
  STATUS=$(echo "$RESULT" | jq -r '.status')
  ISSUES=$(echo "$RESULT" | jq -r '.checks[] | select(.status != "pass") | "• " + .message' | tr '\n' '\\n')

  MESSAGE="{
    \"text\": \"⚠️ Domain Alert: $DOMAIN\",
    \"attachments\": [{
      \"color\": \"$([ \"$STATUS\" == \"warning\" ] && echo \"warning\" || echo \"danger\")\",
      \"fields\": [
        {\"title\": \"Status\", \"value\": \"$STATUS\", \"short\": true},
        {\"title\": \"Domain\", \"value\": \"$DOMAIN\", \"short\": true},
        {\"title\": \"Issues\", \"value\": \"$ISSUES\", \"short\": false}
      ]
    }]
  }"

  curl -X POST -H 'Content-type: application/json' --data "$MESSAGE" $WEBHOOK_URL
fi
```

---

### 8. Docker Integration

```dockerfile
FROM python:3.11-slim

RUN pip install reveal-tool dnspython

COPY check-domains.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/check-domains.sh

CMD ["/usr/local/bin/check-domains.sh"]
```

```bash
# Run domain checks in container
docker run --rm domain-checker reveal domain://example.com --check
```

---

## Related Documentation

### Reveal Adapter Guides

- **[SSL Adapter Guide](SSL_ADAPTER_GUIDE.md)** - SSL/TLS certificate inspection and health monitoring
- **[MySQL Adapter Guide](MYSQL_ADAPTER_GUIDE.md)** - Database schema, queries, and health checks
- **[Stats Adapter Guide](STATS_ADAPTER_GUIDE.md)** - Codebase metrics and quality analysis
- **[Env Adapter Guide](ENV_ADAPTER_GUIDE.md)** - Environment variable inspection
- **[Git Adapter Guide](GIT_ADAPTER_GUIDE.md)** - Git repository inspection

### Reveal Core Documentation

- **[REVEAL_ADAPTER_GUIDE.md](REVEAL_ADAPTER_GUIDE.md)** - Reveal adapter reference
- **[ADAPTER_AUTHORING_GUIDE.md](ADAPTER_AUTHORING_GUIDE.md)** - How to create adapters
- **[SSL_ADAPTER_GUIDE.md](SSL_ADAPTER_GUIDE.md)** - SSL adapter with health check examples

### External Tools

- **dnspython documentation**: https://dnspython.readthedocs.io/
- **DNS record types**: https://en.wikipedia.org/wiki/List_of_DNS_record_types
- **SSL/TLS certificates**: https://letsencrypt.org/docs/

---

## FAQ

### General Questions

**Q: What's the difference between domain:// and ssl://?**

A: **domain://** focuses on DNS records, domain health, and registrar info. It provides an SSL summary but delegates deep SSL inspection to **ssl://**. Use domain:// for DNS + domain health, use ssl:// for deep certificate inspection.

---

**Q: How do I check if my DNS changes have propagated?**

A: Use `reveal domain://example.com --check`. The propagation check queries all authoritative nameservers and reports if records are consistent. Status "pass" = fully propagated, "warning" = propagation in progress.

---

**Q: Can I use domain:// to modify DNS records?**

A: No. domain:// is read-only (inspection only). Use your DNS provider's API or control panel to modify records.

---

**Q: Why is the propagation check slower than other operations?**

A: Propagation validation queries all authoritative nameservers (typically 2-4 servers) and compares results. This takes 3-6 seconds vs 0.5-1s for basic queries. Use `--check` only when you need propagation validation.

---

**Q: Do I need to install dnspython?**

A: Yes. Run `pip install dnspython`. Without it, DNS operations will fail.

---

### Health Checks

**Q: What do the exit codes mean?**

A:
- `0` = Pass (all checks healthy)
- `1` = Warning (non-critical issues, e.g., SSL expires in 20 days)
- `2` = Failure (critical issues, e.g., domain doesn't resolve, SSL expired)

---

**Q: How often should I run health checks?**

A: Depends on context:
- **Production monitoring**: Every 15-30 minutes
- **Development**: As needed (after DNS changes)
- **CI/CD**: Before/after deployments
- **Manual validation**: After infrastructure changes

---

**Q: What's the difference between basic and advanced checks?**

A: Basic checks (`--check`) validate DNS resolution, nameserver response, propagation, and SSL status. Advanced checks (`--check --advanced`) add deeper SSL validation (certificate chain, extended validation). Advanced checks take 2-3x longer.

---

**Q: Can I check multiple domains at once?**

A: Yes, use batch mode:
```bash
cat domains.txt | sed 's/^/domain:\/\//' | reveal --stdin --batch --check
```

---

**Q: How do I show only problems (hide passing checks)?**

A: Use `--only-failures`:
```bash
reveal domain://example.com --check --only-failures
```

---

### DNS Questions

**Q: How do I extract specific DNS record types?**

A: Use jq:
```bash
reveal domain://example.com/dns --format json | jq '.records.A'
reveal domain://example.com/dns --format json | jq '.records.MX'
```

---

**Q: Can I query specific nameservers?**

A: Not directly in reveal. The propagation check queries all authoritative nameservers automatically. For manual nameserver queries, use:
```bash
dig @ns1.example.com example.com
```

---

**Q: Why does DNS propagation take so long?**

A: DNS propagation depends on TTL (Time To Live) values and nameserver update cycles. Typical propagation:
- Between authoritative nameservers: 5-15 minutes
- Global DNS resolver cache: Up to TTL value (often 1-24 hours)

---

**Q: What DNS record types are supported?**

A: A, AAAA, MX, TXT, NS, CNAME, SOA. These cover 99% of common use cases.

---

### SSL Questions

**Q: Can I check SSL certificate chain with domain://?**

A: domain:// provides SSL status only. For certificate chain, use:
```bash
reveal ssl://example.com/chain
```

---

**Q: Why does my SSL check fail even though the certificate is valid?**

A: Common causes:
- Certificate expired (check expiry date)
- Certificate doesn't match domain (check SAN)
- Certificate chain incomplete (check issuer)
- Port 443 not accessible (firewall/network issue)

Run `reveal ssl://example.com --check --advanced` for detailed diagnosis.

---

**Q: How do I monitor SSL certificate expiry?**

A: Use health checks with monitoring:
```bash
# Cron job (daily check)
0 9 * * * reveal domain://example.com --check --only-failures | mail -s "Domain Health" ops@example.com

# Prometheus metric
domain_ssl_expiry_days{domain="example.com"} < 30
```

---

### Integration Questions

**Q: How do I integrate with CI/CD?**

A: Use exit codes for validation:
```bash
if ! reveal domain://staging.example.com --check; then
  echo "Domain health check failed"
  exit 1
fi
```

See [GitHub Actions Integration](#4-github-actions-integration) for complete example.

---

**Q: Can I export metrics to Prometheus?**

A: Yes, see [Prometheus Exporter](#5-prometheus-exporter) example. Generates metrics like:
```promql
domain_health{domain="example.com"} 1
domain_ssl_expiry_days{domain="example.com"} 45
```

---

**Q: How do I parse results with Python?**

A: Use json output:
```python
import subprocess
import json

result = subprocess.run(
    ['reveal', 'domain://example.com', '--check', '--format', 'json'],
    capture_output=True, text=True
)
data = json.loads(result.stdout)
print(data['status'])
```

See [Python Integration](#2-python-integration) for complete example.

---

### Troubleshooting

**Q: Error "Domain does not resolve (NXDOMAIN)" - what does this mean?**

A: The domain doesn't exist or has no DNS records. Check:
1. Domain registration is active (`whois example.com`)
2. Nameservers are configured at registrar
3. DNS records exist (`reveal domain://example.com/dns`)

---

**Q: Error "Nameservers not responding" - how do I fix this?**

A: Nameservers are unreachable. Check:
1. Nameserver hostnames are correct (`reveal domain://example.com/registrar`)
2. Nameservers are online (`dig @ns1.example.com example.com`)
3. Network connectivity to nameservers

---

**Q: Warning "DNS propagating" - how long should I wait?**

A: Propagation between authoritative nameservers typically takes 5-15 minutes. Wait and re-check:
```bash
sleep 300  # Wait 5 minutes
reveal domain://example.com --check
```

If status is still "warning" after 30 minutes, investigate specific nameserver issues.

---

**Q: My domain health check is slow - how can I speed it up?**

A: Optimization strategies:
1. Use overview instead of `--check` for quick status
2. Cache results (for dashboards/frequent checks)
3. Use batch mode for multiple domains
4. Skip advanced checks unless needed

See [Performance Considerations](#performance-considerations) for details.

---

### WHOIS Questions

**Q: Why doesn't WHOIS work?**

A: WHOIS lookup is not yet implemented. It requires the python-whois package and additional development. Current workaround:
```bash
whois example.com
```

---

**Q: When will WHOIS be implemented?**

A: WHOIS is planned for a future release. Track progress at: https://github.com/reveal-tool/reveal/issues

---

---

**Last Updated**: 2026-02-14
**Adapter Version**: reveal 0.1.0+
**Documentation Version**: 1.0
