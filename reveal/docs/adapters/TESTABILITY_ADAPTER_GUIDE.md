---
title: testability:// Adapter Guide
category: guide
---

# testability:// Adapter Guide

Retired spelling: `testability://<path>` is `patches://<path>?view=pressure`, the same
answer (BACK-2160); it prints a replaced-by note until the cut release. The canonical guide
is the [Testability Pressure Guide](../guides/TESTABILITY_GUIDE.md) (`reveal help://testability`)
and the [patches guide](PATCHES_ADAPTER_GUIDE.md). This file exists only to satisfy V024 (every
registered adapter must have a `docs/adapters/` guide file); it intentionally does not
duplicate content (one home per fact).

All query params, for V027 coherence (full docs in the guides linked above):

```
reveal 'testability://src?tests=tests,integration_tests&top=20&min_patches=3&min_categories=3&include_unresolved=true'
```
