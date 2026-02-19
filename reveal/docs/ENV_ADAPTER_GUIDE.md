---
title: Env Adapter Guide
category: guide
---
# Env Adapter Guide

**Author**: TIA (The Intelligent Agent)
**Created**: 2025-02-14
**Adapter**: `env://`
**Purpose**: Environment variable inspection with auto-categorization and sensitive value redaction

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Core Concepts](#core-concepts)
4. [Output Types](#output-types)
5. [Variable Categories](#variable-categories)
6. [Sensitive Value Handling](#sensitive-value-handling)
7. [Workflows](#workflows)
8. [Integration Examples](#integration-examples)
9. [Security Best Practices](#security-best-practices)
10. [Performance & Best Practices](#performance-best-practices)
11. [Limitations](#limitations)
12. [Troubleshooting](#troubleshooting)
13. [Tips & Tricks](#tips-tricks)
14. [Related Documentation](#related-documentation)
15. [FAQ](#faq)
16. [Version History](#version-history)

---

## Overview

The **env adapter** (`env://`) provides secure environment variable inspection with:

- **Auto-categorization** - Groups variables by type (System, Python, Node, Application, Custom)
- **Sensitive value redaction** - Automatically hides passwords, tokens, API keys
- **Metadata enrichment** - Shows category, length, sensitivity for each variable
- **Security-first design** - Prevents accidental secret exposure in logs/output

### Key Features

- ✅ **Auto-categorization** - Intelligent grouping by System/Python/Node/Application/Custom
- ✅ **Sensitive redaction** - Pattern-based detection (PASSWORD, TOKEN, KEY, SECRET, etc.)
- ✅ **Secure by default** - Sensitive values shown as `***` unless explicitly requested
- ✅ **Metadata** - Variable category, length, sensitivity flag
- ✅ **JSON output** - Machine-readable format for scripting
- ✅ **Zero configuration** - Works out of the box, no setup required

### When to Use

**Use env:// when you need to**:
- Debug environment-related issues (missing variables, wrong values)
- Audit environment for exposed secrets
- Validate configuration across environments (dev/staging/prod)
- Document required environment variables for deployment
- Troubleshoot Python/Node runtime environment issues
- Generate environment reports for compliance

**Don't use env:// when**:
- You need to modify environment variables (use shell `export` instead)
- You need process-level environment (use `ps aux` instead)
- You need historical environment data (env is runtime snapshot only)

---

## Quick Start

### Example 1: List All Variables

View all environment variables grouped by category:

```bash
reveal env://
```

**Output**:
```
Environment Variables (42 total)

System (8 variables):
  HOME: /home/user
  PATH: /usr/local/bin:/usr/bin:/bin
  SHELL: /bin/bash
  USER: user
  LANG: en_US.UTF-8
  PWD: /home/user/project
  TERM: xterm-256color
  EDITOR: vim

Python (5 variables):
  VIRTUAL_ENV: /home/user/.venv
  PYTHONPATH: /opt/python
  PYTHON_VERSION: 3.11.5
  PYTHONUNBUFFERED: 1
  PYTHONDONTWRITEBYTECODE: 1

Application (3 variables):
  DATABASE_URL: *** (sensitive)
  API_KEY: *** (sensitive)
  APP_ENV: production
```

### Example 2: Get Specific Variable

Get value and metadata for a specific variable:

```bash
reveal env://PATH
```

**Output**:
```
Variable: PATH
Category: System
Value: /usr/local/bin:/usr/bin:/bin
Length: 29 characters
Sensitive: No
```

### Example 3: Check Sensitive Variable

Sensitive values are automatically redacted:

```bash
reveal env://DATABASE_URL
```

**Output**:
```
Variable: DATABASE_URL
Category: Application
Value: *** (sensitive)
Length: 87 characters
Sensitive: Yes
```

### Example 4: JSON Output

Export as JSON for scripting:

```bash
reveal env:// --format=json
```

**Output**:
```json
{
  "contract_version": "1.0",
  "type": "environment",
  "source": "system",
  "source_type": "runtime",
  "total_count": 42,
  "categories": {
    "System": [
      {"name": "PATH", "value": "/usr/local/bin:/usr/bin", "sensitive": false, "length": 25},
      {"name": "HOME", "value": "/home/user", "sensitive": false, "length": 10}
    ],
    "Application": [
      {"name": "DATABASE_URL", "value": "***", "sensitive": true, "length": 87}
    ]
  }
}
```

### Example 5: Filter Python Variables

Use jq to filter specific categories:

```bash
reveal env:// --format=json | jq '.categories.Python'
```

### Example 6: List All Sensitive Variables

Find all sensitive variables:

```bash
reveal env:// --format=json | jq '[.categories[] | .[] | select(.sensitive==true)]'
```

---

## Core Concepts

### 1. Auto-Categorization

Variables are automatically grouped into categories:

- **System** - OS-level variables (PATH, HOME, SHELL, USER, etc.)
- **Python** - Python runtime variables (PYTHON*, VIRTUAL*, PYTHONPATH)
- **Node** - Node.js runtime variables (NODE*, NPM*, NVM*)
- **Application** - App-specific variables (APP_*, DATABASE_*, API_*)
- **Custom** - Everything else

**Categorization logic**:
1. **Exact match** - System variables matched against predefined set
2. **Prefix match** - PYTHON*, NODE*, APP_*, DATABASE_*, etc.
3. **Fallback** - Unknown variables go to "Custom" category

### 2. Sensitive Value Detection

Variables are flagged as **sensitive** if their name contains:
- `PASSWORD`
- `SECRET`
- `TOKEN`
- `KEY`
- `CREDENTIAL`
- `API_KEY`
- `AUTH`
- `PRIVATE`
- `PASSPHRASE`

**Case-insensitive** - `password`, `Password`, `PASSWORD` all match.

**Redaction behavior**:
- Sensitive values shown as `***` in output
- Length still reported (useful for validation)
- Actual value never logged or printed (security-first)

### 3. Runtime Snapshot

Environment adapter provides **current runtime environment**:
- Reads from `os.environ` (Python process environment)
- Snapshot at query time (not historical)
- Includes variables set before process started
- Does NOT include variables set in child processes

---

## Output Types

### 1. environment (All Variables)

**When**: Querying `env://` without variable name

**Structure**:
```json
{
  "contract_version": "1.0",
  "type": "environment",
  "source": "system",
  "source_type": "runtime",
  "total_count": 42,
  "categories": {
    "System": [
      {
        "name": "PATH",
        "value": "/usr/local/bin:/usr/bin",
        "sensitive": false,
        "length": 25
      }
    ],
    "Python": [ ... ],
    "Node": [ ... ],
    "Application": [ ... ],
    "Custom": [ ... ]
  }
}
```

**Fields**:
- `total_count` - Total number of environment variables
- `categories` - Variables grouped by category (only non-empty categories included)

### 2. env_variable (Specific Variable)

**When**: Querying `env://VARIABLE_NAME`

**Structure**:
```json
{
  "name": "DATABASE_URL",
  "value": "***",
  "category": "Application",
  "sensitive": true,
  "length": 87,
  "raw_value": null
}
```

**Fields**:
- `name` - Variable name
- `value` - Variable value (redacted if sensitive)
- `category` - Auto-detected category
- `sensitive` - Boolean flag for sensitivity
- `length` - Character count (useful even when redacted)
- `raw_value` - Always `null` via CLI (security protection)

---

## Variable Categories

### System Variables

**Description**: OS-level variables common across Unix/Linux/macOS/Windows

**Examples**:
- `PATH` - Executable search path
- `HOME` - User home directory
- `SHELL` - Default shell
- `USER` - Current username
- `LANG` - Locale settings
- `EDITOR` - Default text editor
- `TEMP` / `TMP` - Temporary directory

**Platform-specific**:
- **Unix/Linux/macOS**: `HOME`, `SHELL`, `USER`, `PWD`, `DISPLAY`
- **Windows**: `USERPROFILE`, `USERNAME`, `COMSPEC`, `SYSTEMROOT`, `WINDIR`

### Python Variables

**Description**: Python runtime and virtual environment variables

**Examples**:
- `VIRTUAL_ENV` - Active virtualenv path
- `PYTHONPATH` - Additional import paths
- `PYTHON_VERSION` - Python version string
- `PYTHONUNBUFFERED` - Disable output buffering
- `PYTHONDONTWRITEBYTECODE` - Skip .pyc generation

**Patterns**:
- Starts with `PYTHON*`
- Starts with `VIRTUAL*`
- Exact match `PYTHONPATH`

### Node Variables

**Description**: Node.js, npm, and nvm variables

**Examples**:
- `NODE_ENV` - Environment (development/production)
- `NODE_PATH` - Module search path
- `NPM_TOKEN` - npm authentication token (sensitive)
- `NVM_DIR` - nvm installation directory

**Patterns**:
- Starts with `NODE*`
- Starts with `NPM*`
- Starts with `NVM*`

### Application Variables

**Description**: Application-specific configuration

**Examples**:
- `APP_ENV` - Application environment
- `DATABASE_URL` - Database connection string (sensitive)
- `REDIS_URL` - Redis connection string
- `API_BASE_URL` - API endpoint

**Patterns**:
- Starts with `APP_*`
- Starts with `DATABASE_*`
- Starts with `REDIS_*`
- Starts with `API_*`

### Custom Variables

**Description**: All other variables not matching above categories

**Examples**:
- User-defined variables
- Third-party tool configurations
- CI/CD platform variables (GITHUB_*, GITLAB_*)
- Cloud provider variables (AWS_*, GCP_*, AZURE_*)

---

## Sensitive Value Handling

### Detection Patterns

Variables are flagged as **sensitive** if name contains (case-insensitive):

| Pattern | Examples |
|---------|----------|
| `PASSWORD` | `DB_PASSWORD`, `ADMIN_PASSWORD` |
| `SECRET` | `JWT_SECRET`, `SESSION_SECRET` |
| `TOKEN` | `API_TOKEN`, `GITHUB_TOKEN`, `NPM_TOKEN` |
| `KEY` | `API_KEY`, `PRIVATE_KEY`, `ENCRYPTION_KEY` |
| `CREDENTIAL` | `AWS_CREDENTIALS`, `DB_CREDENTIALS` |
| `API_KEY` | `STRIPE_API_KEY`, `SENDGRID_API_KEY` |
| `AUTH` | `AUTH_TOKEN`, `OAUTH_SECRET` |
| `PRIVATE` | `PRIVATE_KEY`, `PRIVATE_TOKEN` |
| `PASSPHRASE` | `GPG_PASSPHRASE`, `SSH_PASSPHRASE` |

### Redaction Behavior

**Default** (CLI usage):
- Sensitive values shown as `***`
- Length still reported
- Prevents accidental logging/exposure

**Example**:
```bash
reveal env://DATABASE_URL
```

**Output**:
```
Variable: DATABASE_URL
Value: *** (sensitive)
Length: 87 characters
```

### Show Secrets (Programmatic Only)

**NOT available via CLI** (security protection). Only accessible in code:

```python
from reveal.adapters.env import EnvAdapter

adapter = EnvAdapter()
result = adapter.get_element('DATABASE_URL', show_secrets=True)
print(result['raw_value'])  # Actual value
```

**Why not expose via CLI?**
- Prevents accidental logging in scripts
- Forces explicit handling in code
- Reduces risk of secrets in shell history

---

## Workflows

### Workflow 1: Audit Environment for Secrets

**Scenario**: Check what sensitive data is exposed in environment.

**Steps**:

1. **List all variables**:
   ```bash
   reveal env://
   ```

2. **Extract sensitive variables**:
   ```bash
   reveal env:// --format=json | \
     jq '[.categories[] | .[] | select(.sensitive==true)]'
   ```

3. **Generate report**:
   ```bash
   # Count sensitive variables
   SENSITIVE_COUNT=$(reveal env:// --format=json | \
     jq '[.categories[] | .[] | select(.sensitive==true)] | length')

   echo "Found $SENSITIVE_COUNT sensitive variables"

   # List them
   reveal env:// --format=json | \
     jq -r '[.categories[] | .[] | select(.sensitive==true)] | .[] | .name'
   ```

**Result**: Inventory of exposed secrets for security audit.

### Workflow 2: Debug Python Environment

**Scenario**: Python not finding packages or using wrong interpreter.

**Steps**:

1. **Check virtualenv**:
   ```bash
   reveal env://VIRTUAL_ENV
   ```

2. **Check PYTHONPATH**:
   ```bash
   reveal env://PYTHONPATH
   ```

3. **List all Python variables**:
   ```bash
   reveal env:// --format=json | jq '.categories.Python'
   ```

4. **Compare with expected state**:
   ```bash
   # Expected VIRTUAL_ENV
   EXPECTED="/home/user/.venv"

   # Actual VIRTUAL_ENV
   ACTUAL=$(reveal env://VIRTUAL_ENV --format=json | jq -r '.value')

   if [ "$ACTUAL" != "$EXPECTED" ]; then
     echo "❌ Wrong virtualenv: expected $EXPECTED, got $ACTUAL"
   else
     echo "✅ Virtualenv correct"
   fi
   ```

**Result**: Identify environment configuration issues.

### Workflow 3: Validate Configuration Across Environments

**Scenario**: Ensure dev/staging/prod have correct environment variables.

**Steps**:

1. **Define required variables** (e.g., `required-vars.txt`):
   ```
   DATABASE_URL
   API_KEY
   APP_ENV
   REDIS_URL
   ```

2. **Check all required variables exist**:
   ```bash
   #!/bin/bash
   # validate-env.sh

   MISSING=()

   while read var; do
     VALUE=$(reveal env://"$var" --format=json 2>/dev/null | jq -r '.value')

     if [ -z "$VALUE" ] || [ "$VALUE" == "null" ]; then
       MISSING+=("$var")
     fi
   done < required-vars.txt

   if [ ${#MISSING[@]} -gt 0 ]; then
     echo "❌ Missing required variables:"
     printf '  - %s\n' "${MISSING[@]}"
     exit 1
   else
     echo "✅ All required variables present"
   fi
   ```

3. **Run in each environment**:
   ```bash
   # Dev
   ssh dev-server "bash validate-env.sh"

   # Staging
   ssh staging-server "bash validate-env.sh"

   # Production
   ssh prod-server "bash validate-env.sh"
   ```

**Result**: Automated validation of environment configuration.

### Workflow 4: Generate Environment Documentation

**Scenario**: Document required environment variables for deployment.

**Steps**:

1. **Export current environment**:
   ```bash
   reveal env:// --format=json > current-env.json
   ```

2. **Generate markdown documentation**:
   ```bash
   #!/bin/bash
   # generate-env-docs.sh

   cat > ENV_VARS.md <<'EOF'
   # Environment Variables

   ## Required Variables

   | Variable | Category | Sensitive | Description |
   |----------|----------|-----------|-------------|
   EOF

   # Add each variable
   reveal env:// --format=json | \
     jq -r '.categories[] | .[] |
       "| \(.name) | \(.category // "Unknown") | \(if .sensitive then "Yes" else "No" end) | TODO: Add description |"' \
     >> ENV_VARS.md

   echo "Documentation generated: ENV_VARS.md"
   ```

3. **Review and add descriptions**:
   - Edit `ENV_VARS.md`
   - Add descriptions for each variable
   - Commit to repository

**Result**: Documented environment variable requirements.

### Workflow 5: Security Scan for Hardcoded Secrets

**Scenario**: Ensure no sensitive values are hardcoded in config files.

**Steps**:

1. **Get list of sensitive variable names**:
   ```bash
   reveal env:// --format=json | \
     jq -r '[.categories[] | .[] | select(.sensitive==true)] | .[] | .name' \
     > sensitive-vars.txt
   ```

2. **Search codebase for these names**:
   ```bash
   #!/bin/bash
   # scan-for-hardcoded-secrets.sh

   FOUND=()

   while read var; do
     # Search for variable assignments in code
     MATCHES=$(grep -r "$var\s*=" --include="*.py" --include="*.js" --include="*.yaml" .)

     if [ ! -z "$MATCHES" ]; then
       FOUND+=("$var")
       echo "⚠️  Found $var in code:"
       echo "$MATCHES"
     fi
   done < sensitive-vars.txt

   if [ ${#FOUND[@]} -gt 0 ]; then
     echo "❌ Found ${#FOUND[@]} potentially hardcoded secrets"
     exit 1
   else
     echo "✅ No hardcoded secrets found"
   fi
   ```

**Result**: Detect hardcoded secrets in codebase.

### Workflow 6: CI/CD Environment Validation

**Scenario**: Validate environment before running tests/deployment.

**Steps**:

1. **Create validation script** (`.github/workflows/validate-env.yml`):
   ```yaml
   name: Validate Environment

   on: [push, pull_request]

   jobs:
     validate:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v3

         - name: Install reveal
           run: pip install reveal-toolkit

         - name: Check required variables
           run: |
             # Define required variables
             REQUIRED="DATABASE_URL API_KEY APP_ENV"

             for var in $REQUIRED; do
               VALUE=$(reveal env://"$var" --format=json 2>/dev/null | jq -r '.value')

               if [ -z "$VALUE" ] || [ "$VALUE" == "null" ]; then
                 echo "❌ Missing required variable: $var"
                 exit 1
               else
                 echo "✅ $var present (length: ${#VALUE})"
               fi
             done

         - name: Validate APP_ENV
           run: |
             APP_ENV=$(reveal env://APP_ENV --format=json | jq -r '.value')

             if [[ ! "$APP_ENV" =~ ^(development|staging|production)$ ]]; then
               echo "❌ Invalid APP_ENV: $APP_ENV"
               exit 1
             fi

             echo "✅ APP_ENV valid: $APP_ENV"
   ```

**Result**: Automated environment validation in CI/CD pipeline.

---

## Integration Examples

### 1. jq - JSON Processing

**Extract specific categories**:
```bash
# Get all Python variables
reveal env:// --format=json | jq '.categories.Python'

# Get all sensitive variables
reveal env:// --format=json | \
  jq '[.categories[] | .[] | select(.sensitive==true)]'

# Count variables by category
reveal env:// --format=json | \
  jq '.categories | to_entries | map({category: .key, count: (.value | length)})'

# List variable names only
reveal env:// --format=json | \
  jq -r '.categories[] | .[] | .name'
```

**Filter by length**:
```bash
# Find long values (>100 chars)
reveal env:// --format=json | \
  jq '[.categories[] | .[] | select(.length > 100)]'
```

### 2. Python - Environment Analysis

**Example: Environment report**:
```python
import json
import subprocess
from collections import Counter

# Get environment data
result = subprocess.run(
    ['reveal', 'env://', '--format=json'],
    capture_output=True, text=True
)
data = json.loads(result.stdout)

# Analyze categories
category_counts = {
    cat: len(vars)
    for cat, vars in data['categories'].items()
}

# Count sensitive variables
sensitive_count = sum(
    1 for vars in data['categories'].values()
    for var in vars if var['sensitive']
)

print("Environment Report")
print("=" * 50)
print(f"Total Variables: {data['total_count']}")
print(f"Sensitive Variables: {sensitive_count}")
print()
print("By Category:")
for cat, count in sorted(category_counts.items()):
    print(f"  {cat}: {count}")
```

**Example: Compare environments**:
```python
import json
import subprocess

def get_env_vars():
    """Get environment variables as dict."""
    result = subprocess.run(
        ['reveal', 'env://', '--format=json'],
        capture_output=True, text=True
    )
    data = json.loads(result.stdout)

    # Flatten categories
    vars = {}
    for category in data['categories'].values():
        for var in category:
            vars[var['name']] = var['value']

    return vars

# Get environments (assuming SSH access)
dev_env = get_env_vars()  # Run on dev server
prod_env = get_env_vars()  # Run on prod server

# Compare
dev_only = set(dev_env.keys()) - set(prod_env.keys())
prod_only = set(prod_env.keys()) - set(dev_env.keys())
different = {
    k for k in set(dev_env.keys()) & set(prod_env.keys())
    if dev_env[k] != prod_env[k] and dev_env[k] != '***'
}

print(f"Dev-only variables: {len(dev_only)}")
print(f"Prod-only variables: {len(prod_only)}")
print(f"Different values: {len(different)}")
```

### 3. Shell Scripts - Validation

**Example: Pre-deployment check**:
```bash
#!/bin/bash
# pre-deploy-check.sh

echo "Validating environment..."

# Required variables
REQUIRED=(
  "DATABASE_URL"
  "API_KEY"
  "APP_ENV"
  "REDIS_URL"
  "SECRET_KEY"
)

ERRORS=0

for var in "${REQUIRED[@]}"; do
  VALUE=$(reveal env://"$var" --format=json 2>/dev/null | jq -r '.value')

  if [ -z "$VALUE" ] || [ "$VALUE" == "null" ]; then
    echo "❌ Missing: $var"
    ERRORS=$((ERRORS + 1))
  else
    echo "✅ Present: $var (${#VALUE} chars)"
  fi
done

if [ $ERRORS -gt 0 ]; then
  echo ""
  echo "❌ Environment validation failed ($ERRORS errors)"
  exit 1
fi

echo ""
echo "✅ Environment validation passed"
exit 0
```

### 4. Docker - Environment Inspection

**Example: Inspect container environment**:
```bash
# From host, inspect container
docker exec my-container reveal env:// --format=json > container-env.json

# Analyze
jq '.categories' container-env.json

# Check specific variable
docker exec my-container reveal env://DATABASE_URL
```

**Example: Compare host vs container**:
```bash
# Host environment
reveal env:// --format=json > host-env.json

# Container environment
docker exec my-container reveal env:// --format=json > container-env.json

# Compare
jq -s '.[0].total_count as $host | .[1].total_count as $container |
  {host: $host, container: $container, diff: ($container - $host)}' \
  host-env.json container-env.json
```

### 5. Monitoring - Environment Tracking

**Example: Track environment changes**:
```bash
#!/bin/bash
# monitor-env-changes.sh (cron job)

DATE=$(date +%Y-%m-%d-%H%M%S)
SNAPSHOT_DIR="/var/log/env-snapshots"

# Create snapshot
mkdir -p "$SNAPSHOT_DIR"
reveal env:// --format=json > "$SNAPSHOT_DIR/env-$DATE.json"

# Compare with previous snapshot
PREV=$(ls -1 "$SNAPSHOT_DIR"/*.json | tail -2 | head -1)
CURR="$SNAPSHOT_DIR/env-$DATE.json"

if [ ! -z "$PREV" ]; then
  # Check for differences
  DIFF=$(jq -s '.[0].categories as $prev | .[1].categories as $curr |
    ($prev | to_entries | .[].value | .[] | .name) as $prev_names |
    ($curr | to_entries | .[].value | .[] | .name) as $curr_names |
    {added: [], removed: [], changed: []}' \
    "$PREV" "$CURR")

  # Log changes
  if [ ! -z "$DIFF" ]; then
    echo "Environment changed at $DATE" >> /var/log/env-changes.log
    echo "$DIFF" >> /var/log/env-changes.log
  fi
fi

# Cleanup old snapshots (keep last 30 days)
find "$SNAPSHOT_DIR" -name "env-*.json" -mtime +30 -delete
```

---

## Security Best Practices

### 1. Never Log Sensitive Values

**❌ Bad**:
```bash
# Logs full value to shell history
echo $DATABASE_URL

# Logs to file
env | grep PASSWORD > config.txt
```

**✅ Good**:
```bash
# Automatically redacted
reveal env://DATABASE_URL

# Redacted in output
reveal env:// > env-report.txt
```

### 2. Use Programmatic Access for Secrets

**❌ Bad**:
```bash
# Trying to reveal secrets via CLI (not possible)
reveal env://SECRET_KEY --show-secrets  # Flag doesn't exist
```

**✅ Good**:
```python
# Programmatic access with explicit show_secrets
from reveal.adapters.env import EnvAdapter

adapter = EnvAdapter()
result = adapter.get_element('SECRET_KEY', show_secrets=True)
secret = result['raw_value']  # Use carefully
```

### 3. Audit Sensitive Variable Exposure

**Regular audits**:
```bash
# Weekly check for sensitive variables
reveal env:// --format=json | \
  jq '[.categories[] | .[] | select(.sensitive==true)] | length'

# Alert if >10 sensitive variables
SENSITIVE=$(reveal env:// --format=json | \
  jq '[.categories[] | .[] | select(.sensitive==true)] | length')

if [ $SENSITIVE -gt 10 ]; then
  echo "⚠️  Warning: $SENSITIVE sensitive variables exposed"
fi
```

### 4. Use Environment-Specific Variables

**Pattern**: Prefix with environment name
```bash
# Good: Environment-specific
DEV_DATABASE_URL=...
STAGING_DATABASE_URL=...
PROD_DATABASE_URL=...

# Bad: Shared across environments
DATABASE_URL=...  # Which environment?
```

### 5. Validate Variable Names

**Check for suspicious names**:
```bash
# Find variables that should be sensitive but aren't flagged
reveal env:// --format=json | \
  jq -r '.categories[] | .[] |
    select(.name | contains("PASSWORD") or contains("SECRET")) |
    select(.sensitive == false) |
    .name'
```

---

## Performance & Best Practices

### Performance Tips

**1. Cache environment data** (if querying multiple times):
```bash
# Cache to file
reveal env:// --format=json > env-cache.json

# Query cache
jq '.categories.Python' env-cache.json
```

**2. Filter at query time** (jq is fast):
```bash
# Good: Filter with jq
reveal env:// --format=json | jq '.categories.Python'

# Avoid: Multiple queries
reveal env://PYTHONPATH
reveal env://VIRTUAL_ENV
# ... (slow)
```

### Best Practices

**1. Document required variables**:
- Create `ENV_VARS.md` in repository
- List all required variables with descriptions
- Include example values (non-sensitive)

**2. Use validation scripts**:
- Check required variables exist
- Validate variable formats (URLs, paths)
- Run in CI/CD before deployment

**3. Regular environment audits**:
- Weekly snapshots of environment
- Track changes over time
- Alert on unexpected sensitive variables

**4. Naming conventions**:
- Use consistent prefixes (APP_, DB_, API_)
- Include environment in name (DEV_, PROD_)
- Be explicit about sensitivity (SECRET, TOKEN)

---

## Limitations

### 1. Runtime Snapshot Only

**Limitation**: Shows environment at query time, not historical data.

**Impact**: Cannot see what environment was yesterday/last week.

**Workaround**: Implement snapshot system (see Monitoring integration).

### 2. Process-Local Environment

**Limitation**: Shows reveal process environment, not other processes.

**Impact**: Cannot inspect environment of running web server, etc.

**Workaround**: Run reveal within target process context (e.g., `docker exec`).

### 3. No Modification Support

**Limitation**: Read-only adapter, cannot set/update variables.

**Impact**: Cannot use reveal to configure environment.

**Workaround**: Use shell `export` or config management tools (Ansible, etc.).

### 4. Sensitive Detection is Heuristic

**Limitation**: Pattern-based detection may miss some sensitive variables.

**Example**: `DB_CONN` contains sensitive data but not flagged (no PASSWORD/KEY/etc.)

**Workaround**: Manually audit variables, customize patterns if building tooling.

### 5. No Cross-Environment Comparison

**Limitation**: No built-in comparison across dev/staging/prod.

**Impact**: Must manually export and compare.

**Workaround**: Build comparison scripts (see Integration examples).

---

## Troubleshooting

### Issue 1: Variable not found

**Symptom**:
```bash
reveal env://MY_VAR
# Returns null or error
```

**Cause**: Variable not set in current environment

**Solution**:
```bash
# Check if variable exists
env | grep MY_VAR

# Set variable if needed
export MY_VAR="value"

# Verify
reveal env://MY_VAR
```

### Issue 2: Sensitive value not redacted

**Symptom**: Variable contains "password" but not flagged as sensitive

**Cause**: Pattern not matched (e.g., `DB_CONN` vs `DB_PASSWORD`)

**Solution**: Variable names must contain sensitive keywords. Rename if possible:
```bash
# Not detected
DB_CONN=postgres://user:pass@host

# Detected
DB_PASSWORD=postgres://user:pass@host
DATABASE_URL=postgres://user:pass@host
```

### Issue 3: Empty categories

**Symptom**: Some categories missing from output

**Cause**: No variables in that category (empty categories are omitted)

**Solution**: This is expected behavior. Add variables to see category:
```bash
# Before: No Python category
reveal env://

# After: Python category appears
export PYTHONPATH=/opt/python
reveal env://
```

### Issue 4: JSON output has unexpected structure

**Symptom**: Expecting different JSON format

**Cause**: Output structure is standardized (see Output Types)

**Solution**: Use jq to transform:
```bash
# Transform to name:value dict
reveal env:// --format=json | \
  jq '[.categories[] | .[] | {(.name): .value}] | add'
```

---

## Tips & Tricks

### Tip 1: Quick Environment Summary

```bash
# One-line summary
reveal env:// --format=json | \
  jq -r '"Total: \(.total_count) vars, Categories: \(.categories | keys | join(", "))"'
```

### Tip 2: Export Non-Sensitive Variables

```bash
# Export only non-sensitive variables
reveal env:// --format=json | \
  jq -r '.categories[] | .[] | select(.sensitive==false) |
    "export \(.name)=\"\(.value)\""' > safe-env.sh

# Source in another shell
source safe-env.sh
```

### Tip 3: Find Variables by Pattern

```bash
# Find all variables containing "DATABASE"
reveal env:// --format=json | \
  jq -r '.categories[] | .[] | select(.name | contains("DATABASE")) | .name'
```

### Tip 4: Environment Diff

```bash
# Compare two environment snapshots
jq -s '.[0].categories as $env1 | .[1].categories as $env2 |
  {
    added: [  # Variables in env2 but not env1
      $env2[] | .[] | select(.name as $n | ($env1[] | .[] | .name) | contains($n) | not)
    ],
    removed: [  # Variables in env1 but not env2
      $env1[] | .[] | select(.name as $n | ($env2[] | .[] | .name) | contains($n) | not)
    ]
  }' env1.json env2.json
```

### Tip 5: Generate .env.example

```bash
# Create .env.example from current environment
reveal env:// --format=json | \
  jq -r '.categories[] | .[] |
    if .sensitive then
      "\(.name)=your-\(.name | ascii_downcase)-here"
    else
      "\(.name)=\(.value)"
    end' > .env.example
```

### Tip 6: Validate Variable Formats

```bash
# Check URL variables are valid URLs
reveal env:// --format=json | \
  jq -r '.categories[] | .[] |
    select(.name | endswith("_URL")) |
    select(.value | startswith("http") | not) |
    "⚠️  \(.name) is not a valid URL: \(.value)"'
```

---

## Related Documentation

### Reveal Adapters
- **[Stats Adapter Guide](STATS_ADAPTER_GUIDE.md)** - Codebase metrics and quality
- **[Git Adapter Guide](GIT_ADAPTER_GUIDE.md)** - Repository inspection
- **[AST Adapter Guide](AST_ADAPTER_GUIDE.md)** - Code structure analysis
- **[Imports Adapter Guide](IMPORTS_ADAPTER_GUIDE.md)** - Import graph analysis

### Reveal Core
- **[Quick Start](QUICK_START.md)** - Getting started with reveal
- **[Output Contract](OUTPUT_CONTRACT.md)** - Result structure standards
- **[Recipes](RECIPES.md)** - Common reveal patterns
- **[Agent Help](AGENT_HELP.md)** - AI agent integration guide

---

## FAQ

### Q1: Can I use env:// to set environment variables?

**A**: No, env:// is **read-only**. Use shell `export` to set variables:
```bash
# ❌ Cannot set via reveal
reveal env://MY_VAR=value  # Error

# ✅ Use shell export
export MY_VAR=value
reveal env://MY_VAR  # Verify
```

### Q2: Why is my sensitive variable not redacted?

**A**: Variable name must contain sensitive keywords (PASSWORD, SECRET, TOKEN, KEY, etc.):
```bash
# ❌ Not detected (no keyword)
DB_CONN="postgres://user:pass@host"

# ✅ Detected (contains "PASSWORD")
DB_PASSWORD="postgres://user:pass@host"

# ✅ Detected (contains "URL" after "DATABASE")
DATABASE_URL="postgres://user:pass@host"
```

### Q3: Can I customize categories or sensitive patterns?

**A**: Not via CLI. Categories and patterns are built into the adapter. For custom logic, use the adapter programmatically in Python.

### Q4: How do I reveal sensitive values?

**A**: Not possible via CLI (security by design). Use programmatic access:
```python
from reveal.adapters.env import EnvAdapter

adapter = EnvAdapter()
result = adapter.get_element('SECRET_KEY', show_secrets=True)
print(result['raw_value'])  # Handle carefully
```

### Q5: Why doesn't env:// show variables from .env files?

**A**: env:// shows **runtime environment** (`os.environ`), not file contents. To include .env variables:
```bash
# Load .env first
set -a; source .env; set +a

# Then query
reveal env://
```

### Q6: Can I compare environments across servers?

**A**: Yes, export JSON and compare:
```bash
# Server 1
ssh server1 "reveal env:// --format=json" > server1-env.json

# Server 2
ssh server2 "reveal env:// --format=json" > server2-env.json

# Compare
jq -s '...' server1-env.json server2-env.json
```

### Q7: What's the performance overhead?

**A**: Minimal - reads `os.environ` once (< 1ms). JSON export adds ~10-50ms depending on variable count.

### Q8: Can I exclude certain variables from output?

**A**: Use jq to filter:
```bash
# Exclude system variables
reveal env:// --format=json | \
  jq 'del(.categories.System)'
```

### Q9: Does env:// work in containers?

**A**: Yes! Common pattern:
```bash
# Host query
reveal env://

# Container query
docker exec my-container reveal env://
```

### Q10: How do I generate documentation from environment?

**A**: See [Workflow 4: Generate Environment Documentation](#workflow-4-generate-environment-documentation) for full example.

---

## Version History

### Version 1.0.0 (2025-02-14)
- ✅ Comprehensive env adapter documentation
- ✅ Auto-categorization explained (System, Python, Node, Application, Custom)
- ✅ Sensitive value handling detailed
- ✅ Security best practices
- ✅ 6 detailed workflows
- ✅ 5 integration examples
- ✅ Security-first design documentation
- ✅ 10 FAQ entries

### Related Documentation
- Based on `adapters/env.py` (current version)
- Consolidates 37 references across 7 documentation files

---

**End of Env Adapter Guide**
