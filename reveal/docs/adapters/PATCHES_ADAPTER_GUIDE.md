---
title: patches:// Adapter Guide
category: guide
---

# patches:// Adapter Guide

`patches://` scans Python tests for mock and monkeypatch pressure. It is a
review tool for finding test setup that repeatedly replaces the same production
target, reaches into private helpers, or concentrates many patches in one test.

It does not decide that a patch is bad. Patching clocks, network clients,
certificate probes, subprocesses, or filesystem boundaries can be the right test
shape. The useful signal is repetition and where that repetition overlaps with
production boundary fan-out.

## Quick Start

```bash
reveal patches://tests
reveal 'patches://tests?group=target&limit=20'
reveal 'patches://tests?group=test&min=3'
reveal 'patches://tests?private=true'
reveal 'patches://tests?target=ssl'
```

Use JSON when another tool or agent will rank, filter, or store the result:

```bash
reveal 'patches://tests?group=target&limit=20' --format json
```

## Query Parameters

| Parameter | Values | Purpose |
|-----------|--------|---------|
| `group` | `target`, `test`, `file` | Choose whether repeated patches are grouped by patched target, test function, or file. |
| `limit` | integer | Maximum groups returned. |
| `min` | integer | Minimum patch count required for a group. |
| `target` | string or glob | Keep only patch targets matching the substring or glob. |
| `private` | `true`, `false` | Keep only patches of private/internal targets. |
| `suppress` | `true` (default), `false` | When true, hides `sys.stdout`, `sys.stderr`, `sys.stdin`, `builtins.print`, and `builtins.input` from grouped output. These are always infrastructure noise. Raw scan totals always include them. |

## Detected Forms

The scanner uses Python AST parsing and detects common test patching styles:

```python
@patch("pkg.module.call")
def test_case(mock_call):
    ...

with patch("pkg.module.call"):
    ...

with mock.patch("pkg.module.call"):
    ...

with patch.object(adapter, "_load_state"):
    ...

monkeypatch.setattr("pkg.module.call", fake_call)
monkeypatch.setattr(adapter, "_load_state", fake_loader)
patch.dict(os.environ, {"FEATURE": "1"})
```

Dynamic targets are retained with lower confidence instead of being silently
dropped.

## Reading The Output

`patch_count` is the number of patch uses in the group.

`test_count` is the number of test functions containing those patches.

`private_patch_count` highlights patches of names such as `_load_state`.

`max_patches_in_test` helps find single tests with heavy setup.

`examples` gives file, test, line, raw target, and patch kind so the next command
can jump straight to the test.

## Good Review Questions

- Is this target a real runtime boundary, or is test setup replacing decision
  logic that could be exercised directly?
- Are many tests patching the same private helper?
- Would a small fake collaborator make repeated setup clearer?
- Is this patch protecting the test from network, filesystem, clock, or process
  state?
- Does a patch-heavy test cover too much behavior at once?

## Combined Workflow

Use `reveal testability` when you want patch pressure joined with production
boundary profiles:

```bash
reveal testability src --tests tests
reveal testability src --tests tests --top 20
reveal testability src --tests tests --format json
```

That command points at production functions where repeated patching overlaps
with multiple runtime boundaries such as network calls, persistence, filesystem
state, notifications, clocks, environment reads, process globals, or mutation.

## Limits

- Initial language support is Python tests.
- Static target resolution is best-effort.
- `patch.object(adapter, "name")` can identify the patched symbol but may not
  always know the concrete production module.
- The adapter reports review signals, not CI-failing policy.

## See Also

- `reveal help://testability` - combined workflow guide
- `reveal help://schemas/patches` - JSON schema
- `reveal testability src --tests tests` - patch pressure plus boundary fan-out

