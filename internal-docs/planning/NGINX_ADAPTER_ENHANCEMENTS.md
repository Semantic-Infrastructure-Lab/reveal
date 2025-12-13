# Nginx Adapter Enhancements

**Status:** Proposed
**Priority:** High (Production incident prevention)
**Source:** Session risen-wizard-1209 (2025-12-09)
**Context:** Production nginx routing incident ($8,619+/month site serving wrong content)

---

## Executive Summary

During a production incident investigation (happytailstickers.com serving SIL website instead of sticker shop), `reveal` successfully identified the nginx upstream port mismatch. However, the session revealed 4 high-value enhancements that would make reveal **proactively catch** these configuration errors rather than just display them.

**Current capability:** Structure viewing ✅
**Proposed capability:** Active validation & conflict detection 🎯

---

## Background: The Incident

**What happened:**
- Production site happytailstickers.com ($8,619+/month) was serving the wrong website
- Root cause: `sdms_main` nginx upstream pointing to port 8010 instead of 8000
- Both `sdms_main` and `sil_website_production` upstreams pointed to the same backend port

**How reveal helped:**
```bash
ssh tia-proxy 'reveal /etc/nginx/'                               # Fast structure view
ssh tia-proxy 'reveal /etc/nginx/conf.d/tia-upstreams.conf'     # See upstreams
ssh tia-proxy 'reveal /etc/nginx/conf.d/tia-upstreams.conf sdms_main'  # Extract specific upstream
```

This workflow identified the problem, but required manual cross-referencing of upstreams, site configs, and documentation.

**Full incident details:** `/home/scottsen/src/tia/sessions/risen-wizard-1209/README_2025-12-09_11-21.md`

---

## Proposed Enhancements

### Enhancement 1: Duplicate Backend Detection 🔍

**What:** Flag when multiple upstreams point to the same backend server:port

**Current output:**
```
File: tia-upstreams.conf

Upstreams (20):
  sdms_main (lines 17-37)
  sil_website_production (lines 137-139)
  ...
```

**Enhanced output:**
```
File: tia-upstreams.conf

Upstreams (20):
  sdms_main (lines 17-37)
  sil_website_production (lines 137-139)
  ...

⚠️ DUPLICATE_BACKEND detected:
  • sdms_main → 165.227.98.17:8010
  • sil_website_production → 165.227.98.17:8010

  Both upstreams point to the same backend.
  This often indicates misconfiguration.
```

**Implementation:**
- Parse nginx upstream blocks
- Extract `server` directives
- Group by `host:port`
- Flag duplicates in `--check` mode

**When to run:**
- Automatically when viewing upstreams config
- Explicitly with `reveal /etc/nginx/conf.d/upstreams.conf --check`

**Value:** Instant detection of the exact class of bug that caused the incident

---

### Enhancement 2: Impact Analysis (Cross-Reference Site Configs) 🎯

**What:** Show which site configs reference each upstream

**Current workflow:**
```bash
# Manual cross-reference required
reveal /etc/nginx/conf.d/tia-upstreams.conf sdms_main
cat /etc/nginx/sites-enabled/*.conf | grep sdms_main  # Manual search
```

**Enhanced output:**
```bash
reveal /etc/nginx/conf.d/tia-upstreams.conf sdms_main

upstream sdms_main {
    server 165.227.98.17:8010;
    keepalive 32;
}

📊 Impact Analysis:
  Referenced by:
    • /etc/nginx/sites-enabled/happytailstickers.com.conf (5 locations)
    • /etc/nginx/sites-enabled/admin.happytailstickers.com.conf (2 locations)

  ⚠️ Changes to this upstream affect 2 production domains
```

**Implementation:**
- Parse all files in `/etc/nginx/sites-enabled/`
- Search for `proxy_pass http://<upstream_name>`
- Count occurrences per file
- Display in upstream extraction output

**Value:**
- Know blast radius before making changes
- Understand which sites will be affected
- Prioritize testing based on impact

---

### Enhancement 3: Config History/Diff 📊

**What:** Auto-detect backup files and offer comparison

**Context:** During incident, backup file existed but wasn't checked
```
/etc/nginx/conf.d/tia-upstreams.conf
/etc/nginx/conf.d/tia-upstreams.conf.backup-20251119-011204
```

**Proposed feature:**
```bash
reveal /etc/nginx/conf.d/tia-upstreams.conf --diff-backup

Comparing with: tia-upstreams.conf.backup-20251119-011204
Last modified: 2025-11-19 01:12:04

Changes:
  upstream sdms_main:
    - server 165.227.98.17:8000;  # Original (backup)
    + server 165.227.98.17:8010;  # Current

  Added: upstream sil_website_production
    + server 165.227.98.17:8010;
```

**Implementation:**
- Detect files matching `<filename>.backup*` pattern
- Parse both files
- Compare upstream definitions
- Show structured diff

**Alternative syntax:**
```bash
reveal /etc/nginx/conf.d/tia-upstreams.conf --diff <backup-file>
```

**Value:**
- Quick "what changed?" without manual file comparison
- Instant rollback reference
- Track configuration drift over time

---

### Enhancement 4: Registry Validation ✅

**What:** Validate against canonical port registry (if provided)

**Context:** TIA has canonical service registry at `commands/infrastructure/services.yaml`:
```yaml
services:
  - name: SDMS
    port: 8000
    nginx_upstream: sdms_main

  - name: SIL Website
    port: 8010
    nginx_upstream: sil_website_production
```

**Proposed feature:**
```bash
reveal /etc/nginx/conf.d/tia-upstreams.conf --validate-ports ~/services.yaml

✓ sil_website_production → :8010 (matches registry)
✗ sdms_main → :8010 (registry expects :8000)

  Fix: Change line 18 to "server 165.227.98.17:8000;"

  Registry definition:
    name: SDMS
    port: 8000
    nginx_upstream: sdms_main
```

**Implementation:**
- Accept `--validate-ports <registry-file>` flag
- Parse registry file (YAML or JSON)
- Match upstream names to registry entries
- Compare port numbers
- Report mismatches with fix suggestions

**Configuration option:**
```yaml
# ~/.reveal/config.yaml
nginx:
  port_registry: ~/services.yaml  # Auto-validate if present
```

**Value:**
- **Preventative:** Catch misconfigurations before deployment
- **Automated:** No manual cross-reference needed
- **Actionable:** Suggests exact fix
- **Integration-ready:** Works with CI/CD validation workflows

---

## Implementation Strategy

### Phase 1: Basic Nginx Adapter (Foundation)
**Goal:** Parse nginx config files (upstreams, server blocks, locations)

**Deliverables:**
- Nginx config parser (handles upstreams, servers, locations)
- Structure output for nginx configs
- Element extraction (`reveal nginx.conf upstream_name`)

**Dependencies:**
- None (use regex or lightweight parser)

**Effort:** 2-3 days

---

### Phase 2: Conflict Detection (Enhancement 1)
**Goal:** Flag duplicate backends

**Deliverables:**
- Upstream backend deduplication logic
- Warning output for duplicates
- `--check` mode integration

**Dependencies:**
- Phase 1 (nginx parser)

**Effort:** 1 day

---

### Phase 3: Impact Analysis (Enhancement 2)
**Goal:** Cross-reference site configs

**Deliverables:**
- Parse sites-enabled configs
- Extract proxy_pass references
- Show usage count per upstream
- Impact warnings for high-usage upstreams

**Dependencies:**
- Phase 1 (nginx parser)

**Effort:** 2 days

---

### Phase 4: History/Diff (Enhancement 3)
**Goal:** Compare with backup files

**Deliverables:**
- Backup file detection (*.backup*, *.bak, etc.)
- Upstream-level diff logic
- `--diff-backup` flag

**Dependencies:**
- Phase 1 (nginx parser)

**Effort:** 1-2 days

---

### Phase 5: Registry Validation (Enhancement 4)
**Goal:** Validate against external registry

**Deliverables:**
- `--validate-ports` flag
- YAML/JSON registry parser
- Mismatch detection & reporting
- Config file support (`~/.reveal/config.yaml`)

**Dependencies:**
- Phase 1 (nginx parser)

**Effort:** 2 days

**Optional extras:**
- Auto-detect common registry locations
- Support multiple registry formats
- CI/CD integration examples

---

## Success Metrics

### Technical
- ✅ Parse 100+ real nginx configs without errors
- ✅ Detect duplicate backends with 100% accuracy
- ✅ Impact analysis covers all proxy_pass references
- ✅ Diff detection handles common backup naming patterns
- ✅ Registry validation supports YAML and JSON

### User Impact
- 🎯 Prevents configuration errors before deployment
- 🎯 Reduces incident investigation time (manual → automated)
- 🎯 Increases confidence in nginx changes
- 🎯 Enables CI/CD validation workflows

### Adoption
- 🎯 Featured in TIA infrastructure validation workflow
- 🎯 Documented in nginx best practices guides
- 🎯 GitHub issue/PR demonstrating value
- 🎯 Community requests for similar adapters (apache, haproxy)

---

## Alternative Approaches Considered

### 1. **Dedicated nginx validation tool (vs reveal adapter)**
**Pros:** Purpose-built, comprehensive nginx validation
**Cons:** Yet another tool, doesn't fit reveal's progressive disclosure model
**Decision:** Adapter approach fits reveal's vision and reduces tool proliferation

### 2. **Full nginx parser library (vs lightweight custom parser)**
**Pros:** Handles all nginx edge cases
**Cons:** Heavy dependency, overkill for structure viewing
**Decision:** Start lightweight, add library if needed

### 3. **Real-time validation (vs on-demand)**
**Pros:** Immediate feedback
**Cons:** Requires daemon/file watching, complexity
**Decision:** On-demand is sufficient for v1, real-time can be future enhancement

---

## Integration with TIA Ecosystem

### TIA Infrastructure Validation
**Current workflow:**
```bash
tia infrastructure validate  # Validates containers, services, nginx upstreams
```

**Enhanced with reveal:**
```bash
# In validate.py:
ssh tia-proxy 'reveal /etc/nginx/conf.d/upstreams.conf --check --validate-ports /tmp/services.yaml'
```

**Benefits:**
- Consistent validation across infrastructure components
- Automated detection of port mismatches
- Logged output for audit trail

### CI/CD Integration
```yaml
# .github/workflows/deploy.yml
- name: Validate nginx config
  run: |
    reveal /etc/nginx/conf.d/upstreams.conf --check --validate-ports services.yaml
    if [ $? -ne 0 ]; then
      echo "❌ Nginx validation failed"
      exit 1
    fi
```

---

## Open Questions

1. **Parser choice:** Lightweight regex vs full nginx parser library?
   - **Recommendation:** Start with regex for upstreams (simple syntax), add library if needed for complex configs

2. **Registry format:** YAML, JSON, both?
   - **Recommendation:** Support both, detect format automatically

3. **Should --check be default for nginx configs?**
   - **Recommendation:** Yes for upstreams, optional for other nginx files

4. **Scope:** Just upstreams or all nginx directives?
   - **Recommendation:** Start with upstreams (high ROI), expand to server/location blocks if demand exists

---

## Next Steps

1. ✅ Document enhancements (this file)
2. ⬜ Create GitHub issue for nginx adapter
3. ⬜ Prototype lightweight nginx upstream parser
4. ⬜ Implement Phase 1 (basic adapter)
5. ⬜ Add tests with real-world nginx configs
6. ⬜ Ship v0.x.0 with nginx adapter
7. ⬜ Gather feedback from TIA infrastructure validation usage

---

## References

- **Incident session:** `/home/scottsen/src/tia/sessions/risen-wizard-1209/README_2025-12-09_11-21.md`
- **Session conversation:** `tia session read risen-wizard-1209 --grep "reveal" -C 10`
- **TIA services registry:** `~/src/tia/commands/infrastructure/services.yaml`
- **TIA validation code:** `~/src/tia/commands/infrastructure/validate.py`
- **Reveal roadmap:** `ROADMAP.md`
- **Reveal improvement plan:** `IMPROVEMENT_PLAN.md`

---

**Last updated:** 2025-12-09
**Author:** TIA (via session analysis)
**Status:** Awaiting prioritization & implementation
