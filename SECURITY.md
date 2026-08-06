---
title: Reveal Security Policy
type: documentation
category: security
date: 2025-12-01
---

# Security Policy

## Reporting Security Issues

If you discover a security vulnerability, please email: scottsen@users.noreply.github.com

**Please do not open public issues for security vulnerabilities.**

## What Reveal Does

Reveal is a local code analysis tool that:
- Reads files from your filesystem (read-only)
- Parses code using tree-sitter
- Displays structure and metrics
- **Does not** execute code from analyzed files

## Network Activity

Reveal's own code makes network calls only when a network-oriented feature is
explicitly invoked — `ssl://`, `domain://` (DNS + WHOIS + certificate checks),
`nginx` upstream-reachability checks, `cpanel://` (DNS resolution), `mysql://`
(connects only to a database you point it at), the opt-in `L002` link-checker
rule, or the `reveal-mcp` server (a protocol server for AI agents, network by
design when run) — or, on ordinary commands, an automatic PyPI version check:

- **Version check**: on most commands, reveal checks `pypi.org` once per 24
  hours for a newer release (1s timeout, fails silently, never blocks).
  Opt out with `REVEAL_NO_UPDATE_CHECK=1`. Note: the 24h suppression is only
  recorded after a *successful* check — on an offline or firewalled host,
  this means it retries on every invocation rather than backing off.
- **Grammar download (dependency behavior, not reveal's own code)**: the
  `tree-sitter-language-pack` dependency does **not** ship all language
  grammars inside its wheel. The first time reveal parses a file in a
  language it hasn't parsed before on that machine, the pack downloads an
  ~18–21MB platform-specific bundle from
  `github.com/xberg-io/tree-sitter-language-pack` (GitHub Releases),
  SHA256-verified, and caches it at
  `~/.cache/tree-sitter-language-pack/v<version>/`. Subsequent parses of any
  already-cached language are fully offline. This call happens inside a
  compiled Rust extension and is invisible to Python-level network auditing
  (e.g. `sys.addaudithook`) — verify it with `strace`/packet capture instead.
  For air-gapped or network-restricted environments, pre-seed that cache
  directory during image build while network is available (see
  [INSTALL.md](INSTALL.md#network-requirements)).

The list above is not just enumerated from memory — it's verified against
reveal's own source with `reveal surface --type network --source-only`
(taxonomy-based import scan) cross-checked against a full
`reveal 'imports://.' --format json` dump of every import in the codebase
(2,748 imports, 72 unique top-level external modules). No network-capable
import exists outside the adapters/features listed here.

## Security Features

- ✅ Read-only file access
- ✅ No code execution from analyzed files
- ✅ Minimal dependencies (pyyaml, rich, tree-sitter)
- ✅ Path traversal protection via `pathlib`
- ✅ UTF-8 encoding with error handling

Keep updated with: `pip install --upgrade reveal-cli`
