# Nginx Configuration Support in Reveal

**Date:** 2026-01-03
**Status:** Current implementation (regex-based) documented, crossplane enhancement proposed
**Related:** PHASES_3_4_AST_MIGRATION.md (Phase 4 research)

---

## How Nginx Support Works in Reveal

### File Detection

Reveal automatically detects nginx config files by extension:

```bash
# Reveal detects .conf files as nginx configs
reveal /etc/nginx/nginx.conf
reveal /etc/nginx/sites-available/example.conf
reveal /tmp/test.conf
```

**Trigger:** `.conf` file extension
**Analyzer:** `reveal/analyzers/nginx.py` (NginxAnalyzer)
**Registration:** `@register('.conf', name='Nginx', icon='')`

### NOT a URI Scheme

**Important:** Nginx configs are accessed via **file paths**, not URIs.

```bash
# ✅ Correct usage
reveal /etc/nginx/nginx.conf
reveal /path/to/config.conf

# ❌ NOT how it works
reveal nginx:///etc/nginx/nginx.conf     # No nginx:// scheme
reveal nginx://localhost/config          # No nginx:// scheme
```

**Why no nginx:// URI?**
- URI adapters are for **remote/abstract resources** (python://, env://, mysql://)
- Nginx configs are **local files** accessed via file system
- File analyzers use extension detection, not URI schemes

---

## Current Implementation (Regex-Based)

### File: `reveal/analyzers/nginx.py`

**What it extracts:**

1. **Server blocks** (server_name, listen port)
2. **Location blocks** (path, proxy_pass or root)
3. **Upstream blocks** (name only)
4. **Top-level comments** (first 10 lines)

**Example output:**

```bash
$ reveal /etc/nginx/nginx.conf

File: nginx.conf (653B, 37 lines)

Comments (2):
  Line 1: Test Nginx Config
  Line 2: Generated for reveal testing

Servers (2):
  /etc/nginx/nginx.conf:9      example.com www.example.com (port 80)
  /etc/nginx/nginx.conf:27     secure.example.com (port 443 SSL)

Locations (4):
  /etc/nginx/nginx.conf:13     / → http://backend
  /etc/nginx/nginx.conf:18     /api → http://api-service:3000
  /etc/nginx/nginx.conf:22     /static → static: /var/www/static
  /etc/nginx/nginx.conf:34     / → http://backend

Upstreams (1):
  /etc/nginx/nginx.conf:4      backend
```

### Technical Details

**Parser type:** Regex + brace counting state machine

**Extraction logic:**
- Searches for `server {` pattern
- Look-ahead window (20 lines) for server_name and listen
- Searches for `location <path> {` within server blocks
- Look-ahead window (15 lines) for proxy_pass or root
- Searches for `upstream <name> {` at any level

**Limitations:**

1. **Limited look-ahead windows**
   - Server directives must be within 20 lines of `server {`
   - Location directives must be within 15 lines of `location {`
   - May miss directives in large/complex blocks

2. **Upstream names only**
   - Extracts upstream name (`backend`)
   - Does NOT extract backend servers (`192.168.1.10:8080`)

3. **Limited directive extraction**
   - Only extracts: proxy_pass, root
   - Ignores: proxy_set_header, ssl_*, rewrites, limits, etc.

4. **No include support**
   - Cannot follow `include /etc/nginx/conf.d/*.conf;`
   - Only sees directives in the single file

5. **No variable support**
   - Variables like `$backend` shown as literal strings
   - Cannot resolve variable references

6. **Brace counting fragility**
   - Can break on comments with braces: `# server { test`
   - Can break on quoted strings with braces

7. **No SSL details**
   - Detects port 443 → "SSL"
   - Does NOT extract certificate paths, protocols, ciphers

---

## Proposed Enhancement: Crossplane Integration

### What is Crossplane?

**Name:** crossplane
**PyPI:** https://pypi.org/project/crossplane/
**Version:** 0.5.8
**Maintainer:** nginx team
**Purpose:** Parse nginx configs to JSON and back

### How Crossplane Works

```python
import crossplane

# Parse nginx config
payload = crossplane.parse('/etc/nginx/nginx.conf')

# Returns structured JSON:
{
    "status": "ok",
    "errors": [],
    "config": [{
        "file": "/etc/nginx/nginx.conf",
        "parsed": [
            {
                "directive": "http",
                "block": [
                    {
                        "directive": "upstream",
                        "args": ["backend"],
                        "block": [
                            {"directive": "server", "args": ["192.168.1.10:8080"]},
                            {"directive": "server", "args": ["192.168.1.11:8080"]}
                        ]
                    },
                    {
                        "directive": "server",
                        "block": [...]
                    }
                ]
            }
        ]
    }]
}
```

### What Crossplane Adds

**Complete directive extraction:**
- ✅ ALL directives in config (not just proxy_pass/root)
- ✅ Upstream backend servers
- ✅ SSL certificate paths and configuration
- ✅ Headers (proxy_set_header, add_header, etc.)
- ✅ Rewrites, redirects, rate limits
- ✅ Complete request routing logic

**Advanced features:**
- ✅ Follows `include` directives automatically
- ✅ Handles nginx variables correctly
- ✅ Validates nginx syntax (detects errors)
- ✅ Handles complex nested blocks (map, geo, split_clients)
- ✅ Preserves line numbers for error location

**Architecture:**
- ✅ Maintained by nginx team (authoritative)
- ✅ Production-tested (used by nginx tooling)
- ✅ Handles all nginx syntax edge cases

---

## Comparison: Current vs Crossplane

### Test Config

```nginx
http {
    upstream backend {
        server 192.168.1.10:8080;
        server 192.168.1.11:8080;
    }

    server {
        listen 80;
        server_name example.com www.example.com;

        location / {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        location /api {
            proxy_pass http://api-service:3000;
            proxy_read_timeout 60s;
        }
    }

    server {
        listen 443 ssl;
        server_name secure.example.com;

        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;

        location / {
            proxy_pass http://backend;
        }
    }
}
```

### Current Output

```
Servers (2):
  Line 9: example.com www.example.com (port 80)
  Line 27: secure.example.com (port 443 SSL)

Locations (2):
  Line 13: / → http://backend
  Line 18: /api → http://api-service:3000

Upstreams (1):
  Line 4: backend

❌ Missing:
  - Upstream backend servers (192.168.1.10, 192.168.1.11)
  - SSL certificate paths
  - proxy_set_header directives
  - proxy_read_timeout
  - ssl_protocols
```

### With Crossplane

```
Servers (2):
  Line 9: example.com, www.example.com (port 80)
    ✅ 2 server_name values (parsed as array)
  Line 27: secure.example.com (port 443 ssl)
    ✅ SSL: cert=/etc/nginx/ssl/cert.pem, protocols=TLSv1.2,TLSv1.3

Locations (2):
  Line 13: /
    ✅ proxy_pass: http://backend
    ✅ proxy_set_header: Host $host
    ✅ proxy_set_header: X-Real-IP $remote_addr
  Line 18: /api
    ✅ proxy_pass: http://api-service:3000
    ✅ proxy_read_timeout: 60s

Upstreams (1):
  Line 4: backend
    ✅ Backend servers:
      - 192.168.1.10:8080
      - 192.168.1.11:8080
```

---

## Implementation Plan

### Phase 1: Optional Dependency

**Goal:** Add crossplane as optional feature

```toml
# pyproject.toml
[project.optional-dependencies]
nginx = ["crossplane>=0.5.8"]
```

**Installation:**
```bash
# Standard install (regex parser only)
pip install reveal

# With crossplane support
pip install reveal[nginx]
```

### Phase 2: Dual-Mode Analyzer

**Goal:** Use crossplane if available, fallback to regex

```python
# reveal/analyzers/nginx.py
class NginxAnalyzer(FileAnalyzer):
    @staticmethod
    def _has_crossplane():
        try:
            import crossplane
            return True
        except ImportError:
            return False

    def get_structure(self, **kwargs):
        if self._has_crossplane():
            return self._get_structure_crossplane(**kwargs)
        else:
            return self._get_structure_regex(**kwargs)

    def _get_structure_crossplane(self, **kwargs):
        """Use crossplane for complete parsing."""
        import crossplane

        try:
            payload = crossplane.parse(str(self.path))
        except Exception as e:
            # Fallback on crossplane errors
            return self._get_structure_regex(**kwargs)

        # Navigate JSON structure and extract all directives
        servers = []
        locations = []
        upstreams = []

        for config in payload['config']:
            for directive in config.get('parsed', []):
                if directive['directive'] == 'http':
                    servers.extend(self._extract_servers(directive['block']))
                    upstreams.extend(self._extract_upstreams(directive['block']))

        return {
            'servers': servers,
            'locations': locations,
            'upstreams': upstreams,
        }

    def _get_structure_regex(self, **kwargs):
        """Fallback regex parser (current implementation)."""
        # Keep existing implementation as fallback
        ...
```

### Phase 3: Enhanced Output

**Goal:** Show all extracted directives

```python
def _extract_server_block(self, server_directive):
    """Extract complete server configuration."""
    server = {
        'line': server_directive.get('line', 1),
        'listen': [],
        'server_name': [],
        'ssl': {},
        'locations': [],
        'directives': {}
    }

    for directive in server_directive.get('block', []):
        if directive['directive'] == 'listen':
            server['listen'].extend(directive['args'])
        elif directive['directive'] == 'server_name':
            server['server_name'].extend(directive['args'])
        elif directive['directive'].startswith('ssl_'):
            # Extract all SSL directives
            server['ssl'][directive['directive']] = directive['args']
        elif directive['directive'] == 'location':
            location = self._extract_location_block(directive, server)
            server['locations'].append(location)
        else:
            # Capture ALL other directives
            server['directives'][directive['directive']] = directive['args']

    return server
```

---

## Usage Examples

### Basic Structure

```bash
# Works with either parser (regex or crossplane)
reveal /etc/nginx/nginx.conf

# With crossplane: shows complete directive tree
# Without crossplane: shows basic structure (current)
```

### Extract Specific Server

```bash
reveal /etc/nginx/nginx.conf server example.com

# Shows complete server block configuration
```

### JSON Output

```bash
reveal /etc/nginx/nginx.conf --format json

# With crossplane: complete directive tree in JSON
# Without crossplane: basic structure in JSON
```

### Validation

```bash
reveal /etc/nginx/nginx.conf --check

# With crossplane: validates nginx syntax
# Without crossplane: basic structure check
```

---

## Migration Benefits

### For Users Without Crossplane

**Behavior:** Same as current (regex parser)
**Output:** Basic structure (server names, locations, upstreams)
**Impact:** No change

### For Users With Crossplane

**Behavior:** Enhanced parsing
**Output:** Complete directive tree
**Benefits:**
- See upstream backend servers
- See SSL configuration
- See ALL directives (headers, timeouts, rewrites, etc.)
- Syntax validation
- Follows includes

### For TIA Infrastructure

**Current visibility:**
```
3 nginx configs
  → 5 server blocks
  → 12 location blocks
  → 3 upstreams
```

**With crossplane:**
```
3 nginx configs (+ 15 included files)
  → 5 server blocks (with SSL config)
  → 12 location blocks (with all directives)
  → 3 upstreams → 15 backend servers across 4 regions
  → Complete request routing logic
  → Certificate expiration visible
```

---

## Technical Decisions

### Why Optional Dependency?

**Pro:**
- ✅ No breaking changes
- ✅ Users choose their level of detail
- ✅ Keeps reveal lightweight by default
- ✅ Clear upgrade path

**Con:**
- ⚠️ Two codepaths to maintain
- ⚠️ Documentation complexity

**Decision:** Optional is best - allows gradual adoption

### Why NOT nginx:// URI?

**Considered:** `nginx://localhost/config` or `nginx:///path/to/config`

**Rejected because:**
- ❌ Nginx configs are local files, not remote resources
- ❌ URI schemes are for abstract resources (python modules, env vars, databases)
- ❌ File path works perfectly: `reveal /etc/nginx/nginx.conf`
- ❌ Would need to duplicate file system access logic
- ❌ Inconsistent with how other config files work (.yaml, .toml, .json)

**Pattern:** Local files → file path, Remote/abstract resources → URI

### Why Fallback to Regex?

**Scenario:** Crossplane fails to parse

**Options:**
1. Fail hard (show error)
2. Fallback to regex parser
3. Show partial results

**Decision:** Fallback to regex

**Reasoning:**
- ✅ Graceful degradation
- ✅ Better user experience (some info > no info)
- ✅ Handles edge cases (custom nginx syntax)
- ✅ Proven pattern (Phase 3 markdown migration)

---

## File Extensions

**Nginx config extensions recognized:**
- `.conf` (primary, registered now)
- Future: Consider `.nginx` if needed

**Detection logic:**
```python
@register('.conf', name='Nginx', icon='')
class NginxAnalyzer(FileAnalyzer):
    ...
```

---

## Testing Plan

### Test Suite

1. **Regex parser tests** (existing)
   - Verify current functionality preserved
   - All edge cases covered

2. **Crossplane parser tests** (new)
   - Parse complex configs
   - Extract upstream servers
   - Extract SSL configuration
   - Extract all directive types
   - Handle includes
   - Handle variables
   - Validate syntax errors

3. **Fallback tests** (new)
   - Crossplane fails → regex succeeds
   - Crossplane not installed → regex works
   - Invalid nginx syntax → graceful handling

### Real-World Configs

Test with actual nginx configs:
- `/etc/nginx/nginx.conf` (system default)
- TIA infrastructure configs
- Popular open-source projects (Ghost, WordPress, etc.)

---

## Documentation Updates

### User Documentation

**Update:** README.md, usage guide

**Add:**
```markdown
### Nginx Configuration Files

Reveal can analyze nginx configuration files:

```bash
# Basic structure
reveal /etc/nginx/nginx.conf

# Extract specific server block
reveal /etc/nginx/nginx.conf server example.com

# JSON output
reveal /etc/nginx/nginx.conf --format json
```

**Enhanced Support (Optional):**

Install crossplane for complete directive extraction:

```bash
pip install reveal[nginx]
```

With crossplane, you get:
- Upstream backend servers
- Complete SSL configuration
- All directives (headers, timeouts, rewrites, etc.)
- Syntax validation
- Automatic include following
```

### Developer Documentation

**Update:** ANALYZER_PATTERNS.md

**Add Pattern 9:** Optional dependency pattern with fallback

---

## Timeline

**Effort Estimate:** ~1 day (6-8 hours)

**Breakdown:**
- 2 hours: Implement crossplane parser
- 2 hours: Test with real configs
- 2 hours: Documentation
- 1 hour: Test suite updates
- 1 hour: Integration testing

**Priority:** Medium (nice-to-have for v1.0)

---

## Search Keywords

nginx, crossplane, config-parser, optional-dependency, fallback-pattern, directive-extraction, upstream-backends, ssl-configuration, include-support, syntax-validation

---

## Related Documents

- `PHASES_3_4_AST_MIGRATION.md` - Phase 4 research on parsers
- `ANALYZER_PATTERNS.md` - Pattern 8 (AST migration)
- `reveal/analyzers/nginx.py` - Current implementation
- `/tmp/nginx_analyzer_comparison.md` - Concrete comparison (testing artifact)

---

**End of Documentation**
