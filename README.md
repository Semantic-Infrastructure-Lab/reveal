# Reveal

Reveal shows the structure of code, documents and data before their content,
so engineers and AI agents can read only what a question needs. It runs locally.

```bash
pip install reveal-cli
reveal src/                         # what is here?
reveal src/app.py                   # what does this file contain?
reveal src/app.py main             # read this function
reveal calls src/ --callers main   # what connects to it?
reveal src/app.py main --boundary  # what does it read and touch?
reveal check src/                   # which rules find problems?
```

## Start with the question

| Step | Question | Command |
|---|---|---|
| Orient | What is here? | `reveal DIR` or `reveal overview DIR` |
| Structure | What does this contain? | `reveal FILE` |
| Content | Show me one thing | `reveal FILE FUNCTION`, `reveal DOC.md "Heading"`, `reveal FILE :20-40` |
| Relations | What connects to it? | `reveal calls DIR --callers NAME`, `reveal imports DIR --importers FILE` |
| Behavior | What does this function touch? | `reveal FILE FUNCTION --boundary` or `--effects` |
| Judgment inputs | Where should I look closer? | `reveal metrics DIR --hotspots`, `reveal check DIR` |

Search with enclosing structural context: `reveal src/ --grep 'timeout'`.
Use `--format json` for machine-readable results. Counts name their scope and
counting rule; warnings disclose incomplete analysis and coverage limits.
Static name candidates and classified effects do not prove runtime behavior.

## One tool per question

These are current spellings. Where a noun has a subcommand, it and its URI form
use the same execution path. Quote URI arguments containing shell operators.

| Tool | Question / example |
|---|---|
| `overview` | Compact project map: `reveal overview .`; compare with `--against REF` |
| `ast://` | Code elements: `reveal 'ast://src/?complexity>10&sort=-complexity&limit=10'` |
| `calls` | Callers/callees: `reveal calls src/ --callees main --depth 2 --detail` |
| `imports` | Import relationships: `reveal imports src/ --importers app.py` |
| `git://` | History: `reveal 'git://.?type=history&message~=fix'` |
| `markdown://` | Documents: `reveal 'markdown://docs/?body-contains=retry'` |
| `metrics` | File size, complexity and churn: `reveal metrics src/` |
| `check` | Rule findings: `reveal check src/`; a change: `reveal check --changed main..HEAD` |
| `surface` | Recognized external boundaries: `reveal surface src/` |
| `contracts` | Interfaces and data contracts: `reveal contracts src/` |
| `patches` | Test patch pressure: `reveal patches tests/` |
| `diff://` | Structural comparison: `reveal diff://before.py:after.py` |
| `pack` | Context within a budget: `reveal pack src/ --budget 8000` |
| `json://` | Nested JSON: `reveal json://config.json/service/mode` |
| `sqlite://` | Database structure: `reveal sqlite:///path/to/app.db` |
| `xlsx://` | Workbook structure: `reveal xlsx://book.xlsx` |
| `env://` | Environment inspection with secret redaction: `reveal env://NAME` |

Other resources: `reveal help://adapters` lists session exploration and hosting
operations. Hosting adapters remain available and are planned to move to
`reveal-ops`; nginx configuration analysis stays in core. No server or API key
is required for local file inspection.

## Install and discover

Git history, architecture comparisons and churn need the Git extra:

```bash
pip install "reveal-cli[git]"
reveal --agent-help                  # agent orientation
reveal help://quick                  # choose a tool
reveal help://languages              # supported languages and formats (live registry)
reveal help://schemas/ast            # one tool's exact controls
reveal calls --help                  # this subcommand's options
```

If a managed Windows machine blocks the generated executable, use
`python -m reveal`. To pre-download grammars for offline use, run `reveal offline`.

## Scripting and agents

```bash
reveal src/app.py main --format json
git ls-files '*.py' | reveal --stdin
reveal pack src/ --since main --budget 8000
```

Exit codes on qualified operations: **0** completed, **1** a findings gate
matched, **2** invalid invocation/resource, **3** required analysis or output
failed or was incomplete. Incompleteness takes priority over findings.
See [output diagnostics](reveal/docs/OUTPUT_DIAGNOSTICS_GUIDE.md) and each
tool's help for its supported controls and remaining legacy exceptions.

The optional `reveal-mcp` server exposes inspection tools to MCP clients;
[setup and transport details](reveal/docs/guides/MCP_SETUP.md) describe its scope.
Reveal reads, checks and packages context; it does not edit source or run an LLM.

## Evidence and documentation

- [Validation](VALIDATION.md): measured populations, independent oracles and limits.
- [Roadmap](ROADMAP.md): command consolidation and planned behavior changes.
- [Quick start](reveal/docs/QUICK_START.md) and [recipes](reveal/docs/guides/RECIPES.md).
- [Agent reference](reveal/docs/AGENT_HELP.md) and [all documentation](reveal/docs/INDEX.md).
- [Contributing](CONTRIBUTING.md).

## License

MIT; see [LICENSE](LICENSE).
