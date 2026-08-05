---
title: testability:// Adapter Guide
category: guide
---

# testability:// Adapter Guide

Pointer stub — the canonical guide is
[Testability Pressure Guide](../guides/TESTABILITY_GUIDE.md)
(`reveal help://testability`), which now also documents the `testability://`
URI form (BACK-959). This file exists only to satisfy V024 (every registered
adapter must have a `docs/adapters/` guide file); it intentionally does not
duplicate content — see `internal-docs/DOCS.md`'s "one home per fact" rule.

All query params, for V027 coherence (full docs in the guide linked above):

```
reveal 'testability://src?tests=tests,integration_tests&top=20&min_patches=3&min_categories=3&include_unresolved=true'
```
