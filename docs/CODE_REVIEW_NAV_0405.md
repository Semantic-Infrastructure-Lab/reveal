---
title: "Code Review — Nav Features (cunning-griffin-0405)"
type: reference
beth_topics:
  - reveal
  - nav
  - code-review
session: cunning-griffin-0405
date: 2026-04-05
---

# Code Review: Sub-Function Nav Features

Review of `warming-tempest-0405` work: `--outline`, `--scope`, `--varflow`, `--calls`.
Source: `reveal/adapters/ast/nav.py`, `reveal/file_handler.py`, `reveal/cli/parser.py`, `tests/adapters/test_ast_nav.py`.

All 7261 tests pass at review time. Items 1–6 resolved in `coastal-hurricane-0405` — 7262 tests passing after fixes.

---

## Status Legend

- `[ ]` — not started
- `[~]` — in progress
- `[x]` — done

---

## Fix: Correctness Bugs

### [x] 1. Augmented assignment misses the READ (`nav.py:385–397`)

`x += 1` emits WRITE for `x` and READ for `1`. The read of `x`'s *current value* is never emitted.
Semantically correct: augmented assign should produce both WRITE and READ for the left-hand side.

```python
# current — WRITE only for x
_walk_var(left, ..., 'WRITE')
_walk_var(right, ..., 'READ')

# correct — also emit READ for x
_walk_var(left, ..., 'WRITE')
_walk_var(left, ..., 'READ')   # x is also consumed
_walk_var(right, ..., 'READ')
```

`test_augmented_assignment_is_write` only asserts WRITE — update it to assert both.

---

### [x] 2. Depth guard inconsistency (`nav.py:183–199, 222–231`)

`ALTERNATIVE_NODES` recurse when `depth <= max_depth` (recurses at exactly max_depth into depth+1).
`SCOPE_NODES` recurse when `depth < max_depth` (stops at max_depth).

At `depth == max_depth`, an `else` branch emits interior at `depth+1`; a nested `for` does not.
Intent unclear — needs a consistent rule.

Fix: pick one boundary and apply it uniformly. Add a test:
```python
assert all(i['depth'] <= max_depth for i in items)
```

---

## Fix: Dead Code

### [x] 3. Delete dead `_find_func` in tests (`test_ast_nav.py:29–50`)

Never called — all call sites use `_find_func_with_text`. Body is also broken (loop `break` always returns `None`). Delete it.

---

### [x] 4. Delete/consolidate `_condition_text` (`nav.py:98`)

Defined but never called. `_node_label` (line 112) reimplements the same truncation logic inline.
Either have `_node_label` call `_condition_text` (DRY), or delete `_condition_text`.

---

## Fix: Behavioral Ambiguity

### [x] 5. `SCOPE_NODES` / `ALTERNATIVE_NODES` overlap + frozenset duplicates (`nav.py:26–48`)

`elif_clause`, `else_clause`, `except_clause`, `finally_clause`, `catch_clause` appear in **both** sets.
- In `_collect_outline`: safe — ALTERNATIVE is checked first.
- In `_find_ancestors` (line 302): these show up in scope chains. Intentional? Undocumented.

Also: `if_statement`, `for_statement`, `while_statement` are listed twice in `SCOPE_NODES` (silent dedup by frozenset — harmless but confusing).

Fix: remove frozenset duplicates. Add a test pinning `except` scope chain behavior:
```python
# line inside except block — does except_clause appear in chain?
```

---

## UX: Error Messages

### [x] 6. Nav flag without element silently drops the flag (`file_handler.py:294–298`)

`reveal file.py --scope` (no `:LINE`) falls through to normal output with no error.
Same for `--varflow` and `--calls`.

Should emit: `Error: --scope requires an element (e.g. reveal file.py :123 --scope)`

---

## Documentation

### [x] 7. `--outline` behavioral fork is undocumented (`parser.py:260`, `file_handler.py:162`)

- `reveal file.py --outline` → old hierarchical outline (class/method tree)
- `reveal file.py my_func --outline` → new nav control-flow skeleton

Completely different outputs, no hint in help text. Users copying hierarchical syntax get unexpected results.

Fix options (pick one):
- Document the fork in the `--outline` help string
- Use a distinct flag name (`--skeleton` or `--cf`) for the nav variant

---

## Test Gaps

### [x] 8. No integration tests for `handle_file` nav dispatch path

The 45 unit tests in `test_ast_nav.py` test pure functions in isolation. Nothing tests the full dispatch:
`_has_nav_flag → _dispatch_nav → printed output`

Add tests for:
- `reveal file.py :123 --scope` → scope chain output is printed
- `reveal file.py --scope` (no element) → error or documented fallthrough
- `reveal file.py my_func --outline` → nav outline, not hierarchical

---

### [x] 9. `_parse_line_range` edge cases untested

Missing test coverage for:
- Negative numbers
- `START > END`
- Start/end exceeding function line bounds

---

## Future / Low Priority

### [ ] 10. Decompose `_walk_var` (complexity 35, `nav.py:361–466`)

106 lines, complexity 35. Not wrong, but a maintenance burden. Each handler block is a candidate:
`_walk_for`, `_walk_with`, `_walk_assignment`, etc., dispatched via dict.

---

### [x] 11. `_find_element_node` doesn't handle `Class.method` syntax (`file_handler.py:202–206`)

Matches bare names only. `reveal file.py MyClass.my_method --outline` fails silently (returns None).
Users copying hierarchical output directly will get confusing errors.

Fix: either parse dot-syntax and filter on parent class name, or document the limitation in help text.

---

### [ ] 12. `handle_file` complexity 29 — growing dispatch chain

Nav is the 11th branch. No guard against conflicting flags. Not introduced by this PR, but each addition raises risk. Low urgency.

---

## Completed

- **1** Augmented assign READ — fixed + deduplication updated to `(line, col, kind)` + pre-existing `id()` bug in `processed` sets fixed to use byte spans
- **2** Depth guard — `<=` → `<` for ALTERNATIVE_NODES in both `_collect_outline` and `_collect_scope_interior`
- **3** Dead `_find_func` — deleted from `test_ast_nav.py`
- **4** Dead `_condition_text` — deleted from `nav.py`
- **5** `SCOPE_NODES` frozenset duplicates removed; overlap with `ALTERNATIVE_NODES` documented with comment
- **6** UX errors added: `--scope`/`--varflow`/`--calls` without element now exit 1 with a clear message (`--outline` intentionally allowed without element for file-level structure)
- **11** `Class.method` syntax — `_find_element_node` now handles `MyClass.my_method` by reusing existing `PARENT_NODE_TYPES` + `_find_child_in_subtree` from `display/element.py`. "Not found" error now includes a `Class.method` hint.
