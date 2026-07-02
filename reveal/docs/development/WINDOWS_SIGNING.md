---
title: "Windows Code Signing — SignPath Foundation Plan"
type: architecture
status: superseded
superseded_by: internal-docs/releasing/WINDOWS_TRUST_AND_DISTRIBUTION.md
beth_topics:
  - reveal
  - windows
  - distribution
  - signing
  - signpath
  - packaging
---

> **Superseded (2026-06-22).** The current Windows trust playbook lives in the maintainers'
> internal docs (not published in this repo).
> Two things in this doc are now known to be wrong:
> - **PyInstaller `--onefile`** (Phase 3) — this extracts Python to a temp dir at launch, which is an AV heuristic. A signed `--onefile` binary had its signing certificate suspended (Nuitka #3842). Use **Nuitka `--standalone`** instead.
> - **"Azure Trusted Signing is ~$10/mo — not chosen"** — this is now the recommended path; the active CI workflow uses it. SignPath Foundation remains a valid free-OSS alternative (see below) but requires manual approval per release.
>
> The **Phase 2 `__main__.py` workaround** and **SignPath Foundation** notes below are still accurate and worth keeping as reference.

# Windows Code Signing — SignPath Foundation Plan

## The Problem

Reveal is distributed via pip, which generates a `reveal.exe` console script wrapper at install time. This wrapper is unsigned — pip synthesises it from a template and there is no hook to sign it post-generation. On Windows machines with Application Control Policy (ACP/WDAC) set to "publisher-based" or "unsigned file" blocking (common in managed enterprise and developer workstations), this causes:

1. **`reveal.exe` blocked on install or upgrade** — every new binary triggers ACP review
2. **`tree-sitter-language-pack` native DLL blocked on upgrade** — new `.pyd` binaries from version bumps are blocked until whitelisted by hash

These are structurally unsolvable through pip alone. The community consensus for CLI tools that need to work on strict Windows environments: **distribute a signed binary outside pip**.

Observed concretely on a user's Windows machine (2026-05-25): upgrading `reveal-cli` from 0.90.1 → 0.97.0 via pip broke the tool entirely. Rolled back to 0.90.1 and left it there.

---

## The Solution: SignPath Foundation + PyInstaller

### Two-track distribution

| Track | Mechanism | Signed? | For whom |
|---|---|---|---|
| pip | `pip install reveal-cli` | No (status quo) | Linux/macOS devs, CI, non-ACP Windows |
| GitHub Releases binary | `reveal.exe` (PyInstaller bundle) | **Yes** | Windows users on ACP/managed machines |

The signed binary is a self-contained PyInstaller bundle — Python runtime, all dependencies, and reveal itself in one file. No install required beyond downloading and running. ACP trusts the publisher cert once; all future signed releases clear automatically.

---

## SignPath Foundation

[SignPath Foundation](https://signpath.org/) provides **free Authenticode code signing for open source projects**. Key properties:

- **Free for OSS** — no monthly fees, no hardware token required
- **HSM-backed** — private key lives on their HSM, never in CI secrets or a `.pfx` file
- **GitHub Actions native** — `SignPath/github-action-submit-signing-request` integrates directly into release workflows
- **Every release requires manual approval** — a SignPath team member reviews each signing request (not automatic)
- **Origin verification** — SignPath validates that signed binaries were built from the declared source repo

### Eligibility checklist (reveal qualifies)

- [x] OSI-approved license (MIT)
- [x] No commercial dual-licensing
- [x] No proprietary components
- [x] Actively maintained
- [x] Already released publicly
- [x] Functionality described on download page
- [x] Binary artifacts built verifiably from source (GitHub Actions)

### Application process

1. Fill out the [SignPath Foundation application form](https://signpath.io/solutions/open-source-community)
2. Submit via email — they review for OSS compliance
3. Once approved: configure SignPath organisation, create signing policy, wire GitHub Actions
4. Approval timeline is not published but typically days-to-weeks for qualifying projects

---

## Implementation Plan

### Phase 1 — Apply to SignPath Foundation

Action: Submit application. Nothing else until approved.

### Phase 2 — Add `__main__.py` (immediate workaround, no cert needed)

Add `reveal/__main__.py` so `python -m reveal` works as a first-class entrypoint. Python itself is ACP-approved on any machine where it's installed; only the generated `.exe` wrapper is blocked. This is a one-file, zero-risk fix that helps ACP-affected users immediately.

```python
# reveal/__main__.py
from reveal.main import main
main()
```

Document `python -m reveal` as the Windows ACP fallback in README and QUICK_START.

### Phase 3 — PyInstaller build in GitHub Actions

Once SignPath approval is in hand, add a `build-windows.yml` workflow:

```yaml
name: Build Windows Binary

on:
  push:
    tags: ['v*']

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install pyinstaller
          pip install -e ".[all]"

      - name: Build with PyInstaller
        run: |
          pyinstaller --onefile --name reveal bin/reveal_entry.py

      - name: Upload unsigned artifact
        uses: actions/upload-artifact@v4
        with:
          name: reveal-windows-unsigned
          path: dist/reveal.exe

      - name: Sign with SignPath
        uses: SignPath/github-action-submit-signing-request@v1
        with:
          api-token: ${{ secrets.SIGNPATH_API_TOKEN }}
          organization-id: ${{ secrets.SIGNPATH_ORG_ID }}
          project-slug: reveal-cli
          signing-policy-slug: release-signing
          artifact-configuration-slug: windows-exe
          github-artifact-id: reveal-windows-unsigned
          wait-for-completion: true
          output-artifact-directory: dist/signed

      - name: Upload signed exe to GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: dist/signed/reveal.exe
```

### Phase 4 — Document and ship

- Add `reveal.exe` download link prominently in README Windows section
- Add to RELEASING.md checklist: confirm signed binary attached to GitHub Release
- Add to QUICK_START.md: Windows users on managed machines → download the signed binary

---

## Alternatives Considered

| Option | Cost | Why not chosen |
|---|---|---|
| Azure Trusted Signing | ~$10/month | Ongoing cost; SignPath Foundation is free |
| EV cert + cloud HSM | $50-100/month + complexity | Significant overhead; overkill for a CLI tool |
| EV cert + hardware token | ~$300-500/year cert + hardware | Incompatible with GitHub-hosted runners |
| Go/Rust rewrite | Language migration | High cost; Python ecosystem is core to reveal's adapter model |
| Stay on pip only | Free | Does not solve ACP-blocked installs; status quo |

---

## ACP Workarounds for Users Today

While signing is not yet implemented, document these in README/QUICK_START:

1. **`python -m reveal`** — once Phase 2 ships, avoids the blocked `.exe` wrapper entirely
2. **`bat` wrapper** — create `reveal.bat` calling `python -m reveal %*`; `.bat` files are not blocked by most ACP policies
3. **Hash whitelist** — IT admins can whitelist the specific `reveal.exe` hash for a given version (per-version, manual, not scalable)
4. **Pin the version** — pin to the last ACP-approved version (`reveal-cli==0.90.1`) until the signed binary ships

---

## References

- [SignPath Foundation for Open Source](https://signpath.io/solutions/open-source-community)
- [SignPath Foundation eligibility terms](https://signpath.org/terms.html)
- [SignPath GitHub Actions integration](https://docs.signpath.io/trusted-build-systems/github)
- [SignPath `submit-signing-request` action](https://github.com/SignPath/github-action-submit-signing-request)
- [PyInstaller code signing recipe](https://github.com/pyinstaller/pyinstaller/wiki/Recipe-Win-Code-Signing)
- [Windows ACP/WDAC overview](https://mundobytes.com/en/complete-guide-to-windows-defender-application-control-wdac/)
- Discovery session: hidden-sword-0525 (2026-05-25)
