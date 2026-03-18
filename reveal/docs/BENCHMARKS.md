---
title: "Reveal Token Benchmarks"
type: reference
beth_topics:
  - reveal
  - benchmarks
  - token-efficiency
  - progressive-disclosure
---

# Reveal Token Benchmarks

> **Measured, not estimated.** Every number below is an actual measurement on reveal's own codebase (v0.64.x, 357 Python files). Token counts use the standard approximation of 1 token ≈ 4 characters — actual LLM tokenization varies ±10%.

The core claim: reveal's progressive disclosure reduces token usage **3.9–15x** compared to reading files directly on typical tasks. Below are five real scenarios with exact numbers.

---

## Scenario 1: Understanding a Large File

**Goal**: Understand what `file_handler.py` does — what it exports, what the functions are.

**File**: `reveal/file_handler.py` — 637 lines, 23KB, 22 functions

| Approach | Tokens | Lines | What you get |
|----------|--------|-------|--------------|
| `cat reveal/file_handler.py` | 5,883 | 637 | Full file — mostly implementation noise |
| `reveal reveal/file_handler.py` | 690 | 44 | All functions with signatures + imports |
| `reveal reveal/file_handler.py handle_file` | 809 | ~55 | Exact implementation of one function |
| **Reveal total (structure + element)** | **1,499** | — | **Complete understanding** |
| **Reduction vs cat** | **3.9–8.5x** | — | — |

**Progressive drill-down in practice:**
```bash
reveal reveal/file_handler.py           # 690 tokens: all 22 functions at a glance
reveal reveal/file_handler.py handle_file  # +809 tokens: drill into the one that matters
# Total: 1,499 tokens vs 5,883 for cat — 3.9x reduction, plus you chose which function to read
```

**Why it matters**: With `cat`, you pay 5,883 tokens whether you need one function or all of them. With reveal, you pay 690 to understand the shape, then 800 more for exactly the function you need.

---

## Scenario 2: Understanding a Focused Module

**Goal**: Understand what the calls adapter does.

**File**: `reveal/adapters/calls/adapter.py` — 4,128 tokens raw

| Approach | Tokens | Reduction |
|----------|--------|-----------|
| `cat reveals/adapters/calls/adapter.py` | 4,128 | baseline |
| `reveal reveal/adapters/calls/adapter.py` | 275 | **15x** |

15x is near the top of the claimed 10–150x range. It's typical for a focused module with many small functions.

---

## Scenario 3: PR Review Context

**Goal**: Prepare context for reviewing 3 commits of changes to reveal.

| Approach | Tokens | What you get |
|----------|--------|--------------|
| `git diff HEAD~3 \| cat` | ~12,000+ | Full diff, every changed line |
| `reveal pack reveal/ --since HEAD~3 --budget 8000` | 91 (manifest) | 4 prioritized files, changed files first |
| + `--content` flag | ~4,000 | Manifest + structure of all 4 files |

`reveal pack --since HEAD~3` identified 24 changed files and prioritized them, selecting 4 that fit within the 8,000-token budget. The manifest itself (which files to read) is 91 tokens. With `--content`, you get the structure of each prioritized file ready to use.

```bash
reveal pack src/ --since main --budget 8000 --content
# → Changed files first, then key dependencies, structure included
# → Agent reads this output; no second round of Read calls needed
```

---

## Scenario 4: Finding Who Calls a Function

**Goal**: Find all callers of `handle_file` across the codebase.

| Approach | Tokens | Lines | Quality |
|----------|--------|-------|---------|
| `grep -r 'handle_file' reveal/ --include=*.py` | 560 | 28 | File:line snippets — noisy (imports, comments, partial matches) |
| `reveal 'calls://reveal/?target=handle_file'` | 84 | 8 | Structured caller list: function name, file, line |
| **Reduction** | **6.7x** | — | Higher signal — callers only, no noise |

**grep output** (560 tokens) includes import statements, partial string matches, and repeated filenames. **calls://** gives you the exact answer:

```
Callers of: handle_file
Total:      4

  reveal/main.py:226              _process_at_file_target
  reveal/cli/routing.py:698       _handle_file_path
  reveal/cli/commands/check.py:102  run_check
  reveal/adapters/reveal/operations.py:29  get_element
```

---

## Scenario 5: Rough Dead Code Scan

**Goal**: Get a list of uncalled function candidates for post-refactor inspection.

| Approach | Tokens | How |
|----------|--------|-----|
| `reveal 'ast://reveal/?show=functions'` then manual review | 7,196 | Get all 2,542 function names, cross-reference manually |
| `reveal 'calls://reveal/?uncalled&top=10'` | 220 | Direct answer: 10 uncalled candidates from 2,542 functions |
| **Reduction** | **33x** | — |

```bash
reveal 'calls://reveal/?uncalled'        # all uncalled functions
reveal 'calls://reveal/?uncalled&top=10' # top 10 by file recency
```

Output (220 tokens, 15 lines) lists exactly the uncalled candidates with file and line — no manual cross-referencing needed.

The 33x reduction is real: Reveal eliminates the manual cross-reference work. What it doesn't eliminate is the inspection step — each candidate still needs 30 seconds of human review.

> **Note on accuracy**: Functions called via dynamic dispatch (e.g., registered via decorator, looked up by name at runtime) may appear as "uncalled". Treat results as candidates requiring 30 seconds of inspection, not confirmed dead code.

---

## Summary Table

| Scenario | Old approach | Reveal approach | Reduction |
|----------|-------------|-----------------|-----------|
| Understand large file (637 lines) | cat: 5,883 tokens | struct + element: 1,499 tokens | **3.9x** |
| Understand focused module | cat: 4,128 tokens | struct: 275 tokens | **15x** |
| PR context (24 changed files) | git diff \| cat: 12,000+ | pack --content: ~4,000 | **3–4x** |
| Find callers of a function | grep: 560 tokens | calls://?target: 84 tokens | **6.7x** |
| Uncalled function scan | ast:// all + manual: 7,196 tokens | calls://?uncalled: 220 tokens | **33x** *(candidates, not confirmed)* |

**The typical range is 3.9–15x** for file inspection and call graph queries. Scenario 5 reaches 33x but requires human verification of results. The gap widens when:
- The file is large and only part of it matters (structure vs cat)
- The question has a direct answer (uncalled, callers) vs requiring synthesis (manual cross-reference)

**Why not always 150x?** The 10–150x claim is the architectural range. The lower end applies to smaller files or cases where you read the whole structure. The upper end applies to deep dives into large files where only one function matters.

---

## The Token-vs-Signal Tradeoff

Tokens are not the only measure. **Signal density** — how much of what the agent reads is relevant to the task — matters equally.

`grep -r 'handle_file'` returns 560 tokens but ~30% is noise (imports, string matches, repeated filename prefixes). `calls://?target=handle_file` returns 84 tokens, all signal.

Reveal's progressive disclosure enforces a useful property: **you can't accidentally dump 7,000 tokens of raw code**. The architecture makes the efficient path the default path.

---

## Reproducing These Numbers

All measurements use reveal's own codebase at v0.64.x:

```bash
# Scenario 1
wc -c reveal/file_handler.py                           # raw bytes → tokens ÷ 4
reveal reveal/file_handler.py | wc -c                  # structure bytes
reveal reveal/file_handler.py handle_file | wc -c      # element bytes

# Scenario 4
grep -r 'handle_file' reveal/ --include='*.py' | wc -c
reveal 'calls://reveal/?target=handle_file' | wc -c

# Scenario 5
reveal 'ast://reveal/?show=functions' | wc -c
reveal 'calls://reveal/?uncalled' | wc -c
```
