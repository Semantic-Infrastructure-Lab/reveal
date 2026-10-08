---
title: "Reveal Install Guide: optional extras and network requirements"
type: guide
beth_topics:
  - reveal
  - install
  - extras
  - air-gapped
  - network
help_topic: install
help_description: "Optional extras (pygit2, MySQL, DNS, MCP...) and network requirements for air-gapped installs"
help_category: getting_started
---

# Reveal Install Guide: optional extras and network requirements

`pip install reveal-cli` is enough for structure, outline, extraction, nav flags, `check`,
and most adapters. This guide covers what it does NOT include (the optional extras) and what
needs the network (air-gapped and CI setups). For the quick install steps, platforms and
troubleshooting see [INSTALL.md](https://github.com/Semantic-Infrastructure-Lab/reveal/blob/main/INSTALL.md).

## Optional extras

Install one with `pip install "reveal-cli[<extra>]"`, several with
`pip install "reveal-cli[git,database]"`. The names below are the keys of
`[project.optional-dependencies]` in `pyproject.toml`.

| Extra | Installs | Needed for | Without it |
|-------|----------|-----------|------------|
| `git` | `pygit2` | the `git://` adapter and `git://` refs in `diff://` | `git://` fails with `git:// adapter requires pygit2` and the install command |
| `database` | `pymysql` | the `mysql://` adapter (there is no postgres adapter) | `mysql://` fails with `pymysql is required for mysql:// adapter` |
| `dns` | `dnspython` | `domain://` views `/dns`, `/mail`, `/ns-audit` | those views fail with `dnspython is required for DNS operations` |
| `whois` | `python-whois` | `domain://` views `/whois`, `/registrar` | the view fails with `python-whois not installed`; `/dns` still works |
| `mcp` | `mcp` | the `reveal-mcp` server (see `reveal help://mcp`) | `reveal-mcp` exits 1 with `requires the 'mcp' package` |
| `html` | `lxml` | faster HTML parsing | none; HTML falls back to the stdlib `html.parser` |
| `powerpivot` | `pbixray` | full schema/DAX from modern Power BI `xlsx://` data models | Excel 2010/2013 models still work; modern ones report limited schema and ask for `reveal-cli[powerpivot]` |
| `xlsx` | `openpyxl` | building `.xlsx` test fixtures only | none; the `xlsx://` adapter reads workbooks without it |
| `treesitter` | nothing | deprecated no-op kept so old install commands still resolve | n/a (tree-sitter ships by default) |
| `dev` | pytest, black, ruff, plus the packages the adapter tests need | contributing | n/a |
| `all` | everything in `git`, `database`, `dns`, `whois`, `mcp` and `html` | every adapter and `reveal-mcp` in one install (e.g. an offline container) | n/a |

`all` deliberately leaves out `powerpivot`: it pulls in about 100 MB of pandas/numpy, and
its `xpress9` dependency ships prebuilt wheels for x86_64 Linux only, so elsewhere it needs a
compiler. Add it explicitly if you read modern Power BI models:
`pip install "reveal-cli[all,powerpivot]"`. `all` also skips `xlsx`, `treesitter` and `dev`,
which no runtime feature needs.

## Network requirements

`pip install reveal-cli` needs PyPI as usual. After that reveal only touches the network for
explicitly network-oriented features (`ssl://`, `domain://`, nginx upstream checks, `cpanel://`,
`mysql://`, the opt-in `L002` link checker, the `reveal-mcp` server) and a daily PyPI update
check (disable with `REVEAL_NO_UPDATE_CHECK=1`).

### The tree-sitter-language-pack grammar download (plan for this in air-gapped hosts)

The `tree-sitter-language-pack` dependency does not ship every grammar inside its wheel. The first
time reveal parses a language it has not parsed on that machine, the pack downloads a
platform-specific grammar bundle from GitHub Releases (`github.com` and
`release-assets.githubusercontent.com`) and caches it under
`~/.cache/tree-sitter-language-pack/v<pack version>/`. After that first fetch that language, and
any other already cached, parses fully offline. The bundle is tens of megabytes and its size varies
by pack version (19 MB to 135 MB across the versions cached on one development machine).

### Pre-seeding the cache for CI sandboxes, containers and air-gapped hosts

On a machine that has network access, while building the base image:

```bash
pip install reveal-cli            # or "reveal-cli[all]" so no adapter is missing an extra offline
reveal offline --languages python,javascript,go   # only what you need
reveal offline                                    # or every grammar the pack ships (much larger)
reveal offline --disable-update-check             # also stop the daily PyPI check permanently
# then copy ~/.cache/tree-sitter-language-pack/ into the restricted image
```

`reveal offline --disable-update-check` persists `REVEAL_NO_UPDATE_CHECK` into
`~/.config/reveal/config.yaml`. `reveal offline` wraps the pack's own `download()` and
`download_all()`; calling those directly works too.

### Egress allowlist

CI needs `pypi.org` and `files.pythonhosted.org` (pip install) plus `github.com` and
`release-assets.githubusercontent.com` (grammar bundle). A PyPI-only allowlist lets the install
succeed and the first real parse of a new language hang or fail.

### What a failed download looks like

reveal reports the failure rather than degrading silently: a `WARNING`-level log before the fetch
attempt, `--explain-file` reports the grammar is not cached instead of claiming full support, and
`--format json` carries an explicit `"error"` key instead of an ambiguous empty structure
(BACK-979).

## See also

- `reveal help://mcp` for `reveal-mcp` setup, `reveal help://git`, `reveal help://mysql` and
  `reveal help://domain` for the adapters the extras unlock
- `reveal help://config` for `REVEAL_*` environment variables and `~/.config/reveal/config.yaml`
