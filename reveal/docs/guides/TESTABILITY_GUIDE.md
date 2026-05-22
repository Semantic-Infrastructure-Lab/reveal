---
title: Testability Pressure Guide
category: guide
help_topic: testability
help_description: "Test patch pressure joined with production boundary fan-out (reveal testability)"
help_category: feature_guides
help_token_estimate: "~2,000"
---

# Testability Pressure Guide

Use this workflow when tests need many patches or when a production function
mixes business decisions with runtime boundaries such as network clients,
persistence, notifications, clocks, environment, filesystem state, or global
state.

The goal is not to say "mocking is bad." Mocking external boundaries is often
correct. The goal is to find review targets where repeated patching and
boundary fan-out overlap.

## Quick Start

```bash
# Raw patch pressure in tests
reveal patches://tests
reveal 'patches://tests?group=target&limit=20'

# Combined workflow: test patches + production boundaries
reveal testability src --tests tests
reveal testability src --tests tests --top 20
reveal testability src --tests tests --format json
```

Read the output as a ranked review queue:

- high repeated patch count means tests often replace the same target
- private target patches can mean tests are reaching through internals
- boundary categories show runtime effects in related production functions
- suggestions are advisory, not automatic refactor instructions

## What It Finds

`patches://` scans Python tests with AST parsing and detects:

- `@patch("pkg.mod.name")`
- `patch("pkg.mod.name")`
- `mock.patch("pkg.mod.name")`
- `patch.object(obj, "attr")`
- `monkeypatch.setattr("pkg.mod.name", value)`
- `monkeypatch.setattr(obj, "attr", value)`
- `patch.dict(...)`

`reveal testability` joins those patch groups to production function profiles.
The production side uses a conservative boundary taxonomy:

- network clients and probes
- persistence and state save/load calls
- filesystem writes and runtime paths
- notification and alert calls
- event/telemetry emission
- clocks and sleeps
- environment/config reads
- process/global state
- mutation of objects or collections

## Good Interpretations

Good:

```text
This target is patched 25 times because it is a genuine external certificate
boundary. A fake checker might reduce repeated setup, but patching is normal.
```

Good:

```text
This private helper is patched repeatedly and the related function touches
persistence, notification, clock, and mutation boundaries. Extracting the pure
decision step may make tests simpler.
```

Bad:

```text
There are mocks, therefore the design is wrong.
```

## Useful Follow-Up Commands

```bash
# Inspect a patch-heavy production function
reveal src/module.py function_name --boundary
reveal src/module.py function_name --sideeffects

# Find other complex production functions
reveal 'ast://src?complexity>10&sort=-complexity&limit=20'

# See cross-file calls for a function
reveal 'calls://src?callees=function_name'
reveal 'calls://src?target=function_name'

# Map external surfaces in the codebase
reveal surface src
```

## JSON Output

Use JSON for agents, dashboards, and CI experiments:

```bash
reveal 'patches://tests?group=target' --format json
reveal testability src --tests tests --format json
```

The JSON output includes confidence metadata because static target resolution is
best-effort. Do not treat the report as a precise runtime call graph.

## Limits

- Initial language support is Python tests and Python production code.
- Dynamic patch targets are preserved but may have lower confidence.
- Static target resolution is best-effort.
- Project-specific boundary words may need future config.
- Advisory output is the main surface. CI-failing rules should come later after
  thresholds are tuned for the project.

