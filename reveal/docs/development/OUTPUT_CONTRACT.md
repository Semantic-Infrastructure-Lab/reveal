---
title: Output Contract Specification
category: reference
help_topic: output
help_description: "Output contract specification for adapter authors"
help_category: dev_guides
---
# Output Contract Specification

**Current Version**: 1.1.0
**Status**: Released
**Date**: 2026-02-06
**Stability**: Stable 🟢

## Version History
- **v1.1** (2026-02-06): Added trust metadata (`meta` field)
- **v1.0** (2026-01-17): Initial release with core contract fields

---

## Purpose

This document defines the **Output Contract** for all Reveal adapters and analyzers. It establishes:
- Required fields that MUST be present in all outputs
- Optional recommended fields for common patterns
- Versioning strategy for backwards compatibility
- Validation rules for compliance

**Why this matters:**
- **AI agents** need stable, predictable JSON schemas
- **Contributors** need clear contracts for new adapters
- **Users** can depend on consistent output structure
- **Tool builders** can parse Reveal output reliably

---

## Contract v1.0 Schema

### Required Fields (4)

Every adapter/analyzer output MUST include these fields:

```python
{
    'contract_version': '1.0',     # String: Contract version (semver)
    'type': str,                   # String: Output type (snake_case)
    'source': str,                 # String: Data source identifier
    'source_type': str,            # String: Source category
}
```

#### Field Definitions

**`contract_version`** (required)
- **Type**: String (semantic version)
- **Format**: `"MAJOR.MINOR"` (e.g., `"1.0"`, `"2.1"`)
- **Purpose**: Identifies which contract version the output conforms to
- **Example**: `"1.0"`

**`type`** (required)
- **Type**: String
- **Format**: `snake_case` (lowercase with underscores)
- **Purpose**: Identifies the output schema variant
- **Examples**: `"ast_query"`, `"mysql_server"`, `"environment"`, `"python_structure"`
- **Rules**:
  - Must start with lowercase letter
  - Only lowercase letters, numbers, underscores
  - No leading/trailing underscores
  - Regex: `^[a-z][a-z0-9_]*$`

**`source`** (required)
- **Type**: String
- **Purpose**: Identifies where the data came from
- **Examples**:
  - File: `"src/main.py"`
  - Directory: `"src/"`
  - Database: `"localhost:3306/mydb"`
  - Runtime: `"env://"`
  - URL: `"https://api.example.com"`
- **Paths are spelled as the user named the target** (BACK-1366): `stats://src` and
  `reveal stats src` both report `"source": "src"`, never the resolved
  `/home/<user>/.../src`, and an absolute input stays absolute. Separators are `/` on
  every OS. The URI router, `ResourceAdapter.compose` (for a composed sibling's
  `source`) and the subcommand emitter apply this once, through
  `reveal.utils.results.echo_source`; an adapter that emits other paths it found spells
  them with `reveal.utils.path_utils.as_spelled`. Paths inside a result are either
  relative to `source` (`imports://` files) or spelled from the cwd like `source` itself
  (`ast://`, `markdown://`'s `path`, suggested `next_commands`), so a consumer can always
  resolve them from where it ran reveal. Kept on purpose (BACK-1216): `pack://`'s per-file
  `path` is a drill-back anchor, and `depends://`'s warnings name the absolute scan root
  that climbed. The contract harness
  (`tests/test_output_contract_compliance.py`, invariant `abs_path`) runs every
  registered adapter and subcommand on a relative path and fails on any absolute one.

**`source_type`** (required)
- **Type**: String (enum)
- **Values**: `"file"` | `"directory"` | `"database"` | `"runtime"` | `"network"` | `"unknown"` (a failed result the router built for a source that isn't an existing file or directory)
- **Purpose**: Categorizes the source for filtering/processing
- **Examples**:
  - `"file"` - Single file path
  - `"directory"` - Directory path
  - `"database"` - Database connection
  - `"runtime"` - Runtime/environment state
  - `"network"` - Remote resource

---

### Recommended Optional Fields (5)

These fields are OPTIONAL but recommended for common patterns:

**`metadata`** (optional, dict)
- **Purpose**: Generic counts, timestamps, metrics
- **Examples**:
  ```python
  'metadata': {
      'total_files': 42,
      'total_results': 156,
      'timestamp': '2026-01-17T14:30:00Z',
      'duration_ms': 234
  }
  ```

**`query`** (optional, dict)
- **Purpose**: Applied filters or search parameters
- **Examples**:
  ```python
  'query': {
      'complexity': {'op': '>', 'value': 10},
      'language': 'python'
  }
  ```

**`next_steps`** (optional, list of strings)
- **Purpose**: Progressive disclosure - what to explore next
- **Examples**:
  ```python
  'next_steps': [
      'reveal ast://src/main.py:MainClass',
      'reveal stats://src/ --hotspots'
  ]
  ```

**`status`** (optional, dict)
- **Purpose**: Health/state assessment
- **Examples**:
  ```python
  'status': {
      'health': 'healthy',  # 'healthy' | 'warning' | 'error'
      'warnings': ['Table has no primary key'],
      'errors': []
  }
  ```

**`issues`** (optional, list of dicts)
- **Purpose**: Problems/warnings found during analysis
- **Examples**:
  ```python
  'issues': [
      {
          'code': 'F401',
          'message': 'Unused import',
          'file': 'src/main.py',
          'line': 42
      }
  ]
  ```

---

## Contract v1.1 Schema (Added 2026-02-06)

### Trust Metadata Field

**v1.1 adds the optional `meta` field** for parse quality and confidence information. This enables AI agents to know when to trust results and handle degraded parsing gracefully.

**`meta`** (optional, dict)
- **Purpose**: Parse quality, confidence, warnings, errors
- **Added**: v1.1 (2026-02-06)
- **Backward Compatible**: Yes (v1.0 clients ignore this field)

**Structure:**
```python
'meta': {
    'parse_mode': str,          # How parsing was performed
    'confidence': float,        # 0.0-1.0 overall confidence
    'warnings': [dict],         # Non-fatal issues
    'errors': [dict]            # Fatal issues (with fallback info)
}
```

**Field Details:**

**`meta.parse_mode`** (optional, string)
- **Values**: `"tree_sitter_full"` | `"tree_sitter_partial"` | `"fallback"` | `"regex"` | `"heuristic"`
- **Purpose**: Indicates how the data was parsed
- **Examples**:
  - `"tree_sitter_full"` - Full tree-sitter AST parsing (high confidence)
  - `"tree_sitter_partial"` - Partial tree-sitter parsing (some parse errors)
  - `"fallback"` - Tree-sitter failed, used fallback method
  - `"regex"` - Regular expression extraction
  - `"heuristic"` - Pattern-based heuristics

**`meta.confidence`** (optional, float)
- **Range**: 0.0 (no confidence) to 1.0 (complete confidence)
- **Purpose**: Overall confidence in the results
- **Guidelines**:
  - `1.0` - Perfect parse, all elements extracted correctly
  - `0.95-0.99` - High confidence, minor ambiguities
  - `0.80-0.94` - Good confidence, some elements may be incomplete
  - `0.50-0.79` - Partial results, fallback methods used
  - `< 0.50` - Low confidence, results may be unreliable

**`meta.warnings`** (optional, array of dicts)
- **Purpose**: Non-fatal issues encountered during parsing. `type` is the key every reader uses (`outcome_of`, the truncation and sort notes, the renderers' skip lists). `ResultBuilder`, prepared metadata and `note_warning` reject a warning without a nonempty string `type` with `ValueError`; `code` remains optional. `meta.errors` has a separate contract and does not require `type`.
- **Schema**:
  ```python
  {
      'type': str,         # Kind of warning, snake_case (e.g., 'encoding_uncertain'); required
      'code': str,         # (optional) Stable catalog id (e.g., 'W001', 'W-CALLS-1')
      'message': str,      # Human-readable message
      'file': str,         # (optional) Affected file
      'line': int,         # (optional) Line number
      'suggestion': str    # (optional) How to fix
  }
  ```
- **Examples**:
  ```python
  'warnings': [
      {
          'type': 'encoding_uncertain',
          'code': 'W001',
          'message': 'File encoding uncertain, assumed UTF-8',
          'file': 'legacy.py',
          'suggestion': 'Add # -*- coding: utf-8 -*- header'
      }
  ]
  ```

**`meta.errors`** (optional, array of dicts)
- **Purpose**: Fatal errors that prevented normal parsing
- **Schema**:
  ```python
  {
      'code': str,         # Error code (e.g., 'E002')
      'message': str,      # Human-readable error
      'file': str,         # Affected file
      'line': int,         # (optional) Error location
      'fallback': str      # What fallback method was used
  }
  ```
- **Examples**:
  ```python
  'errors': [
      {
          'code': 'E002',
          'message': 'Parse failed: malformed syntax',
          'file': 'src/broken.py',
          'fallback': 'Used regex fallback'
      }
  ]
  ```

**Complete v1.1 Example:**
```python
{
    'contract_version': '1.1',
    'type': 'ast_query',
    'source': 'src/',
    'source_type': 'directory',

    # NEW in v1.1
    'meta': {
        'parse_mode': 'tree_sitter_full',
        'confidence': 0.95,
        'warnings': [
            {
                'type': 'encoding_uncertain',
                'code': 'W001',
                'message': 'File encoding uncertain, assumed UTF-8',
                'file': 'src/legacy.py'
            }
        ],
        'errors': []
    },

    'results': [
        {
            'symbol': 'authenticate',
            'file': 'src/auth.py',
            'line': 42,
            # Per-item confidence (optional, adapter-specific)
            'confidence': 0.98,
            'parse_warnings': []
        }
    ]
}
```

**Per-Item Confidence** (optional, adapter-specific):
Adapters MAY include confidence/warning fields on individual result items:
- `confidence` (float 0.0-1.0) - Confidence for this specific item
- `parse_warnings` (array) - Item-specific warnings

**When to use v1.1:**
- ✅ Adapter uses tree-sitter or complex parsing
- ✅ Fallback methods are available
- ✅ Results may have varying quality
- ✅ AI agents need to know when to trust results
- ❌ Simple data extraction (no parsing complexity)

---

### Adapter-Specific Fields

Adapters MAY include additional fields beyond the contract. These fields:
- MUST NOT conflict with reserved field names
- SHOULD be documented in adapter help (`reveal 'help://<adapter>'`)
- SHOULD follow naming conventions (snake_case for dicts, lowercase for simple types)

**Example**: MySQL adapter with custom fields
```python
{
    'contract_version': '1.0',
    'type': 'mysql_server',
    'source': 'localhost:3306',
    'source_type': 'database',
    'metadata': {
        'total_tables': 45,
        'total_databases': 3
    },

    # MySQL-specific fields (not in contract)
    'connection_health': {...},
    'innodb_health': {...},
    'replication': {...},
    'tables': [...]
}
```

### Ignored inputs

For a URI/declared dispatch using the shared JSON writer, ignored query inputs and
flags are included in `meta.warnings` before serialization. The parser owns unknown
keys; the flag ledger owns inputs that were accepted but not used by this operation.
Each entry has a `type` and `code` (`unknown_query_param`, `unused_query_param`, or
`unused_flag`), a human-readable `message`, and `fields`: the query keys or flag
spellings concerned. Existing warnings remain in the answer.

These are informational diagnostics and do not make a usable answer fail. An
operation rejected before it could run does not gain an unused-input warning;
parser warnings already authored during preparation remain visible. The JSON
writer does not change execution facts or failure classification. Text dispatches
keep their stderr notes, including recovery hints; equivalent typed commands and
URI queries carry the same structured unused-input facts. JSON file artifacts
beside a text answer also retain these diagnostics.

MCP provenance queries receive the warnings inside the JSON document instead of
an appended stderr suffix. Unrelated stderr retains its existing behavior; this
does not convert arbitrary printed diagnostics into structured warnings.

### Retired spellings (`retired_spelling`)

A spelling the surface program has retired (a flag, subcommand, URI scheme, query parameter
or parameter value, or an MCP tool name) is listed once in `RETIREMENTS` in
`reveal/cli/invocation.py`, with its replacement and a stage. At the `note` stage the command
still answers as before. Its exit code and answer do not change, and it prints one stderr line,
`note: <old> is deprecated; use <replacement>.`, once per invocation. `--format json` stdout stays
one parseable document and carries the same fact as a `meta.warnings` entry:
`{"type": "retired_spelling", "code": "retired_spelling", "message": ..., "field": "<table key>", "old": ..., "replacement": ..., "stage": "note"}`.
`field` is the table key (`flag:--search`, `param:calls.root`, ...), so two retired spellings are
two entries. The MCP server never writes the note to stderr: a JSON result carries the same
entry, and a text result ends with a `[note: ...]` line. At the `error` stage (the cut release) the
same text is an error and the exit code is 2. A `phase7` row is recorded and prints nothing yet.

---

## Outcomes: failed, not applicable, truncated, ok

A result says what happened through two top-level fields and one kind of `meta.warnings`
entry. `reveal.utils.results.outcome_of` is the one definition, and the URI router turns it
into the legacy exit code for adapters, in text and JSON alike (BACK-1059).
Declared operations, including direct hotspots requests, use the explicit policy
below. Legacy subcommands print their results through
`cli/routing/subcommand.emit_subcommand_result`, so a failed or cut answer reads
the same in both forms (BACK-1544). Their command-specific findings policies
apply after this legacy outcome handling:

| Outcome | How the result says it | Exit | Build it with |
|---|---|---|---|
| `failed` | a non-empty top-level `error` string | 1 | `ResultBuilder.create_error(...)` |
| `not_applicable` | `applicable: false` plus a `reason` | 0 | `raise NotApplicableError(reason)` |
| `truncated` | a `meta.warnings` entry `{"type": "truncated", "field", "shown", "total", "exact", "cause", "message"}` per cut list | 0 | `note_truncation(result, field, shown, total, cause)` |
| `ok` | none of these; an empty answer is still `ok` | 0 | `ResultBuilder.create(...)` |

- **Return the error; don't exit or print it.** The router prints `Error (<scheme>://): <error>`
  on stderr before rendering and exits 1 after, so `--format json` still gets the whole
  envelope. A renderer adds only detail for an error result (an example, the valid names)
  and must not print the error again.
- **A raise is the same failure.** Every call the router makes into an adapter (construct,
  `--base-path`, `check`, `get_element`, `get_structure`, `post_process`) goes through
  `cli/routing/uri._call_adapter`, which turns an exception into an error result and handles
  it as above: the error once on stderr, text stdout empty, the envelope in JSON,
  `--output json=PATH` written, exit 1 (BACK-1553). An element lookup that returns `None` fails the
  same way, with the adapter's `available_elements`. Such a result has `type` = the scheme,
  `source_type` `unknown` unless the source is an existing file or directory, and one
  `meta.errors` entry whose `code` (`adapter_error`, `element_not_found`) says the router
  built it. A `NotApplicableError` becomes a `not_applicable` result the same way.
- **Record a raw-list cut; don't print it.** `note_truncation` is the spelling of a raw-list cut
  (`cause`: `limit`, `auto_cap`, `max_items`, `head`, `tail`, `range`). The router records
  its own `--max-items`/`--head` cuts the same way and prints every cut once, after the
  render: `⚠ Truncated <field>: showing N of M — <how to see more>` on stdout for text, on
  stderr for grep. A `?sort=` that did not apply is recorded and printed the same way: a
  `meta.warnings` entry `unknown_sort_field` (no result has the field) or `sort_failed`
  (json:// values that do not compare), `RESULT_CONTROL_WARNINGS` in `utils/results.py`.
  Renderers leave these warnings alone. An adapter that shows a
  composed child's list as its own passes `compose(..., cut_as=(field, hint))`.
- **A cap the adapter applies itself is a cut too.** Count the whole list, then keep the top
  N and record it with the adapter's own knob as the hint (`hint='raise ?top=N'`). Cut where
  the knob is read, not inside a shared helper: a helper that returns only the top N has lost
  the total (`identify_hotspots`, `group_patches` did, BACK-1543). A total field (`total`,
  `total_modules`, `count`) may stay for JSON readers, but it doesn't replace the marker for a raw list. The
  hint can also say how to narrow the question (`help://search`: `raise ?top=N (0 = all), or
  add a search word to narrow it`); a cap with no knob still records the cut and says that.
- **A bounded rows record carries its own presentation proof.** An intrinsic page such as
  overview's graph sections may use `{rows, total, returned, omitted}` instead of repeating
  the same cut in `meta.warnings`. All counts are nonnegative integers; returned equals
  the row-array length, total equals returned plus omitted, and total is the actual uncut
  observed population. Text states those bounds too. Each bounded cycle member/witness
  list has its own record. Source scan limits and input loss still require their separate
  coverage evidence: an exact observed total is not proof of an exhaustive project scan.
  Prefix ordering applies recursively to these pages: selected cycle rows keep their
  identities while their member and witness pages may have independently smaller bounds.
  Diagnostic details and router cuts of raw arrays continue to use `note_truncation`.
- **A cap cuts the answer; it doesn't bound what is read.** Build the whole answer, order it,
  then keep the first N. Stop reading early only when the reading order is the answer's order,
  and then read one past the page: that item proves more exist, so record a lower bound,
  `note_truncation(..., total=shown + 1, exact=False)`, printed `showing 50 of 51+`. git://
  walks history this way, one walk for every view (`git/commits.walk_history`), and reads all of
  it when `?sort=` asks for another order. Before, `?sort=date&limit=3` sorted the 3 commits it
  had walked and listed the 3 newest (BACK-1547). A read that fails partway fails the query; it
  doesn't return what it had as the whole answer.
- **A file's own parser failing is a failed outcome too.** An analyzer whose parser fails
  outright (XML, CSV, a notebook) returns `ResultBuilder.create_error`; the file view
  (`reveal <file>`) reports it through the router's `announce_outcome`/`conclude_outcome`:
  `Error (<path>): <error>` on stderr, the error at the top of the JSON envelope, exit 1
  (BACK-1590). A tree-sitter parse that *recovered* around errors is not a failure: it
  sets `_has_errors`, prints the parse-recovered note, and exits 0.
- **Problems inside an answer are not a failure.** Per-file parse failures in a result that
  was still produced go in `meta.errors` (v1.1). An error on one item of a list stays on that
  item. Neither changes the outcome.
- **A subcommand passes its result to `emit_subcommand_result`; it doesn't print its own
  JSON.** That function adds the envelope (the subcommand's name as `type`, the adapter's
  `contract_version` and `meta` kept) and acts on the outcome. `scripts/check_boundaries.py`
  counts `add_cli_contract_fields()` calls outside it (rule `subcommand-output`), and the count
  may only fall.
- `tests/test_result_outcome.py` and `tests/test_result_truncation.py` pin the definition,
  the exit path and the truncation line; `tests/test_output_contract_compliance.py` runs
  every registered adapter and subcommand against them. Its invariant 7 (`own_cap`) runs each
  adapter with its cap knob at 1 and uncapped, and fails on any list that got shorter without
  a `truncated` entry or a validated bounded-row parent, on a capped list that isn't the uncapped list's first N, and on a
  disclosed `total` that isn't the uncapped length (or, when `exact` is false, is above it).

---

## Declared execution policy

Direct surface, architecture, contracts, deps, hotspots, overview and trace subcommands and their URI equivalents share declared
parameter binding and one answer/emission path. Surface retains `surface_scan`;
Architecture is a deprecated alias of Overview and returns the canonical
`overview` or `overview_diff` identity, with one central retirement note.
Contracts retains `contracts`; deps retains `deps_scan`; hotspots retains `hotspots_scan`;
overview selects `overview` or `overview_diff`; trace retains `trace`.
Their execution policy
uses explicit completeness and failure causes from the analysis owner, independently
of `outcome_of()`'s legacy rendering categories:

| Code | Meaning |
|---|---|
| `0` | Requested work completed without an enabled findings gate matching. |
| `1` | Completed analysis matched a supported adverse-findings gate. |
| `2` | Invalid invocation, resource or parameter. |
| `3` | Required analysis or requested output failed or remained incomplete. |

Ordinary `ast://` filter queries use these same execution facts without generated
parameter bindings (BACK-2338). Rejected query controls, invalid regex or missing resources
produce structured usage errors (`2`). Failed required source analysis, recovered
parses, lost files/directories and requested-output failures give `3`. The AST owner
classifies surviving source structures before filtering: an empty filtered result
does not erase partial loss; zero surviving structures with required loss is failed,
while useful partial observations remain usable through MCP. Healthy empty trees,
expected non-applicability, advisory warnings and presentation cuts remain `0`.
Python API validation still raises `ValueError`. Dedicated `show=dict-heatmap`,
`show=dict-schemas` and nonempty `reveal_type` modes use the same policy
(BACK-2341, BACK-2342), with their own operation identities and required source proof.
Their `analysis` object counts discovered required `candidate_files`, `analyzed_files`,
`failed_files` and `discovery_failures` (directory events, not a missing-file estimate).
Type evidence also records `recovered_files` and advisory `unsupported_files`;
unsupported single-file targets retain their existing scan behavior outside required
Python source counts. Required candidates equal analyzed plus failed files, and recovered
files are a subset of analyzed files. These counts precede observation selection and
schema clustering. No analyzed required source with required loss means failed;
surviving analyzed source with required loss, or any recovered type tree, means incomplete,
even when no observations remain. Healthy empty answers and advisory language-census
failures stay complete. Required loss omits full confidence and carries bounded source
diagnostics. Element/check operations, stdin and mixed batches retain their legacy policy.
This adoption adds no findings gate or generated AST subcommand.

Direct `json://FILE` roots, ordinary filters/controls and navigation/index/slice
requests use owner execution facts. Complete values, including empty and null,
no-match results, warnings and presentation cuts remain `0`; rejected requests,
missing resources or directory misuse are `2`; required read/parse failures and
attempted output failures are `3`. All these answers retain the `json_value`
operation identity. Python library navigation/query rejections now return failed
`json_value` results with explicit `invalid_request` diagnostics, replacing
`json_error`; read/parse errors remain exceptions. Authored selector/control
exceptions are `RequestValidationError`, a `ValueError` subtype. Selector validation
precedes content loading; content loading precedes ordinary control validation.
MCP signals these failures as errors, exposing authored request diagnostics and
masking unexpected parse/analysis failures. Repair markers outrank request-error
evidence; postprocessing cannot manufacture a request rejection from prior work.

Introspection (`schema`, `flatten`, `gron`, `type`, `keys`, `length`), element/check
modes and stdin/batches retain their legacy execution policies. File preflight
resolves the underlying path without parsing selectors: malformed slice diagnostics
now pass through the adapter boundary, including legacy modes (exit `1` there),
instead of raising a preflight traceback. Existing primary-JSON file-mirror
suppression remains. Successful unused-input warning suffixes remain a separate
JSON parseability limitation; this adoption does not suppress them.

Surface is an inventory and declares only `--fail-on none`, also its default; it
rejects `findings`. `none` never suppresses incomplete analysis or output failure.
`unparsed_files` or `recovered_files` make its scan incomplete; taxonomy limitations,
explicit scope exclusions and harmless warnings do not automatically do so. These
facts are evaluated before field projections or presentation cuts. A returned or
raised operational error retains the resolved `surface_scan` identity and exits 3;
an invalid resource/parameter produces a structured error when JSON is requested.
Unknown CLI options rejected by argparse still use stderr usage and empty stdout.

Surface withholds optional `meta.confidence` and adapter-owned `_meta.confidence`
because its former fixed estimates were unmeasured. Existing parse mode, limits,
scope, coverage and diagnostics remain available. Their omission uses the existing
optional-field contract; other adapters' confidence policies and the envelope version
are unchanged. Completeness and exit classification continue to use execution facts,
not the presence of a confidence value.

Overview and its deprecated architecture alias support only `--fail-on none`.
Ordinary scope census errors, import input loss and failed/recovered parses establish
incomplete execution; ranking cuts and harmless warnings do not. Comparison requires
explicit `analysis.complete`, basis and per-side component evidence. Proved-identical
comparisons have empty snapshots; analyzed comparisons require both base/head imports
and complexity states consistent with overall completeness. Required scan caps are
incomplete. Invalid-ref/non-repository requests rejected before analysis retain
`overview_diff` identity and exit 2; operational Git failures exit 3. Missing or
malformed comparison proof cannot become success or be masked by a later usage
diagnostic. Both transports share the canonical shapes and supported controls.
Ordinary `top`, `all` and `verbose` bound or expand the map in text and JSON;
comparison rejects explicitly supplied `no_imports`, `all` and `verbose`, even false.
`pack --architecture` remains a separate live selection control.

Contracts supports only `--fail-on none`. Its `recovered_files`, `unparsed_files`
and producer-owned `E_CONTRACTS_ANALYSIS` errors establish incomplete execution;
surviving arrays and diagnostics remain available. Empty inventories, disclosed
unsupported languages and harmless warnings remain complete. `abstract_only` and
`implementations` affect analysis; `impls` is presentation only and retains complete
JSON arrays plus `impls_cap`. Its default is 5 and zero displays all implementers.
`--impls 3.0` and `?impls=3.0` both mean 3; fractions, negative values, booleans and
scientific notation are invalid. Boolean controls use strict declared conversion.

Deps declares default `none` and supports `findings`, selected from complete,
uncapped circular-group/unused-import counts. Its required `analysis` carrier
retains exact requested components, completeness states, failed/lost counts and
findings counts. Missing, malformed or contradictory proof cannot become success;
returned producer errors remain analysis failures even if labeled invalid request.
Skipped components are excluded from required work. Top and summary-only are
presentation controls: top never shrinks JSON, and summary-only applies solely to
primary JSON after execution facts exist. Text and human-primary artifacts retain
the full map. Both spellings return `deps_scan`; `--fail-on findings` restores the
previous text-mode findings gate. Whole-valued `top=3.0` and `top=1e2` are valid;
CLI `--all` remains rejected, URI `--all` and both `--verbose` expand text only.
Both deps spellings are retired (BACK-1054): each adds a `retired_spelling` warning and
otherwise keeps this shape and these exit codes; the three components are views of one
imports graph build. Imports declares default `none` and supports `findings`: exit 1 when
the `?circular`, `?unused` or `?violations` answer has a row (an incomplete answer exits
3 first); every other imports view has no findings to gate.

Hotspots defaults to `none` and supports `findings` using the owner's pre-cap
`summary.has_findings`: quality below 70 or complexity above 20. Stats coverage
is required in every mode; AST coverage/results are required unless `files_only`.
Missing/malformed proof, errors and `parse_degraded`, `check_rules_failed`,
`analysis_failed`, `parse_recovered` or `analysis_incomplete` warnings prevent successful execution.
With known required loss, positive uncapped Stats file coverage or surviving requested
function observations establishes usable partial work; without either, analysis is
failed. Clean zero populations remain complete. This conservative rule can classify
Stats loss as failed when healthy AST analysis yields no function matching the
requested threshold. Optional churn/test convention warnings, confidence and ranking cuts do not.
Top caps retained JSON and text rankings (zero all); negative top now rejects.
Signed min_complexity remains accepted; whole decimal/scientific numeric values
normalize consistently. Both transports' `--verbose` lifts caps. CLI `--all`
remains rejected; URI `--all` preserves an explicit top. Default text findings
now exit 0; explicit `--fail-on findings` restores the findings gate in either
format and transport. Neither fields nor output cuts erase captured facts.

Ordinary overview supports only `--fail-on none`. Required owners are the recognized-code
census and import analysis unless `no_imports` explicitly requests scope only. It does not
collect Stats, quality rules, complexity rankings or Git history. Qualified graph facts,
counting rules and source coverage are validated before bounded presentation; malformed
required evidence stays failed even at top zero. A validated partial graph and surviving
census can support useful incomplete orientation; wholesale required-owner failure stays
failed. Unsupported extensions and presentation cuts alone do not establish failure.

Top defaults to five and bounds graph rows, cycle members and witnesses in text and JSON;
zero retains observed totals without rows. Diagnostic details have a separate disclosed
five-to-fifty bound. All/verbose expand map rows only. Obsolete no_git/tests controls reject
with corrections toward their existing assessment queries. Exclusions/gitignore apply to
both census and graph. Hidden counts use entries, not an invented skipped-file population.
Validated execution facts survive postprocessing and `--fields`; an explicit field selection
may omit unselected payload sections while failure metadata, exits and MCP error state
remain honest. Human-primary artifacts use the same bounded map.

Overview with `against` selects `overview_diff` before ordinary map collection and
uses the existing comparison engine and comparison evidence qualification. Its live
head is labelled `working tree`. Top controls centroid population (`max(top,1)*4`);
ordinary-only no_imports/all/verbose controls reject. Invalid pre-analysis requests
keep canonical diff identity and exit 2; missing required snapshot proof or output
failure exits 3. Both operation identities retain validated execution facts before
explicit payload selection. Comparison snapshots and materialization use the existing
tracked-base/live-head exclusion and gitignore policies.

Directory enumeration failures collected by Stats, AST, trace, patch scanning and testability
are disclosed as `analysis_incomplete`. Its `count` with `unit: directories` counts
unique identified directories; `directories` and `causes` are bounded to five entries.
Distinct causes for a shown directory remain in its message. When the operating system
supplies no directory name, `unknown_directory_events` counts those error callbacks
separately; they do not increase the identified-directory count. Neither count estimates
the unknown missing file population. Policy exclusions are separate from I/O loss.
Stats retains these invocation-local diagnostics before filters, empty returns and
projections; direct legacy Stats exit behavior is unchanged. Overview and Hotspots
consume required Stats and AST loss before execution classification. Review recognizes
propagated directory loss as incomplete (exit 3), ahead of any finding. A high/critical
finding alone exits 1 (`overall_status` stays `fail`); exit 2 is usage rejection only (BACK-2051).
This does not yet add `--fail-on` to Review.
This is bounded consumer coverage: Classify, other walkers and the Calls, Contracts and transitive
side-effect collection carriers are not yet qualified for directory failure disclosure.

A policy exclusion that leaves an analysis nothing to analyze is disclosed as `scope_hidden`
(BACK-2065), so an ignored tree does not read as a clean zero. Imports, Depends, Calls and
Surface add one when their walk kept no candidate file but hid entries by `.gitignore`,
`--exclude` or REVEAL_IGNORE. `count` with `unit: entries` counts what the walk hid the way
the directory view's footer does (a pruned directory once, not its contents), `hidden` maps
each cause to its count, `causes` lists them, and `suggestion` is `--no-gitignore` when
gitignore is one. The `message` uses the footer's wording (`N entries hidden by .gitignore
(use --no-gitignore to show)`) and is printed once with the other warnings. It is not loss:
confidence and the outcome are unchanged, and a walk that kept any file reports nothing.
Depends walks from the project root, so it judges this at its target: nothing left to analyze
at the requested file or directory, with the target (or a directory holding it) hidden, is
disclosed even when the project has other files (BACK-2075).

Inspection failure for an ambiguous `build`/`dist` directory does not prove noise,
including a missing child from a stale listing. Normal descent remains eligible:
it may recover, or its error reaches the qualified traversal consumers above.
If inspection fails transiently and descent succeeds, otherwise-noise nested source
may conservatively enter the population. Reserved noise, known virtualenv markers
and explicit exclusion policies keep their rules. This does not qualify the other
walkers and consumers listed above.

Calls indexes built from known traversal-incomplete structure collections are
returned for the current request but are evicted rather than cached. This guard applies at
cache write and when explicitly supplied structures with known traversal loss would
otherwise reuse a matching warm hit. An index with a file skipped for an environmental
reason (an `OSError`, a lost worker) is likewise returned but not cached, since a recovered
file keeps its mtime and size. Healthy warm hits, including empty indexes,
retain their existing reuse behavior. The cheap directory-mtime/scope key does not
detect every file change. General warm/deep freshness, separate reference caches
and full Calls directory diagnostics remain outside this bounded repair.

Shared AST file analysis also discloses required parser loss as `analysis_failed`:
an existing `parse_error` (including an empty message), malformed consumed analyzer
output, or required `meta.errors` survives flattening into the answer. Usable
observations from the existing owned categories remain alongside the attributed
failure; arbitrary metadata does not prove usable partial analysis. Clean empty
structures, supported cached artifacts and optional import enrichment retain their
existing behavior. This is a producer repair, not an exhaustive row-schema validator
or adoption of the declared execution policy by legacy testability reports.

Trace supports only `none`. Required nonempty `from` preserves typed strings and
uses once-only percent decoding for URI scalars without plus decoding. Signed
whole `depth` defaults to 2 and clamps to 1–5; booleans, fractions and scientific
notation reject. Local proof validates renderer-consumed frames and nonnegative
edge totals without equating edge counts to frame counts. Definitive root absence
requires the canonical unresolved placeholder, zero totals and no known required
input failures/recovery/malformed evidence. It is usage 2; incomplete evidence
wins with 3. Postprocessing cannot fabricate absence from earlier successful or
incomplete analysis. Facts and safe authored absence diagnostics survive field
selection. Proven absence remains a normal MCP response for compatibility;
required output failure overrides that exception. Legacy mixed batches keep their
existing outcome policy.

Human-primary `--output json=PATH` uses the same result as primary JSON. A requested
artifact write failure is disclosed on stderr and in `meta.output_errors`, while the
primary result remains available and the exit is 3. Primary `--format json` retains
its existing `--output json=PATH` no-op. Closing stdout alone keeps the conventional exit 0;
it cannot erase an independent analysis or artifact failure.

Native `reveal check` (single file, directory and `--stdin --check`) follows the same artifact
rule through the one owner, `write_requested_artifact` (`utils/json_utils.py`), which is
flag-agnostic: a requested `--output json=PATH` write that fails is disclosed once on stderr and exits 3,
over findings (1) and over the legacy `--exit-zero` (`check_exit_code(..., output_failed=True)`
through `execution_exit_code`). The report is printed in full first. Primary `--format json`
keeps the `--output json=PATH` no-op, so check's JSON never carries `meta.output_errors`.

The reusable owner API is `ExecutionFacts`, `AnalysisCompleteness`, `FailureCause`,
`merge_execution_facts()` and `execution_exit_code()` in `utils.results`. Producers
supply completeness and adverse findings explicitly; aggregate facts before mapping
codes. Do not infer them from numeric child exits, arbitrary warnings or nonempty
lists. `NOT_STARTED` records rejected/unattempted work without asserting successful
analysis. Legacy `outcome_of()` behavior remains unchanged.

Adoption is explicit in `Invocation`'s command catalog. Other commands, adapter-specific
checks, file views, stdin and mixed URI batches retain their existing policies.
`--fail-on` is rejected on unqualified operations/transports. This section does not
claim those paths have adopted the declared policy.

### Declared parameter bindings

`ParamSpec` owns defaults, converters, bounds, choices, requiredness, zero semantics,
role and optional `CliBinding` metadata. Its historical fixed `cli_flags` mappings keep
their original meaning. A separate `ResourceSpec` owns the positional resource and its
transport defaults. Schema export and generated arguments use those declarations.
Global presentation, exclusions, gitignore and flag accounting retain their existing
owners.

Qualified declared subcommands retain the parser-aware flag ledger but establish
their walk scope once inside the declared runner, after resolving the operation.
An inaccessible resource during scope discovery produces its canonical analysis
failure answer. Legacy subcommands retain their outer dispatch scope unchanged.

`utils.query_binding.bind_declared_params()` accepts original typed values or a raw
URI query. It validates without marking application; `ParamSpec.read()` marks actual
use. Normalized reads do not rerun converters. Replacing a value invalidates its
normalization; mutating a normalized container requires rebinding. Optional percent
scalar and comma-percent list codecs decode exactly once, splitting lists before
item decoding and preserving plus signs. Comma-percent's empty query represents an
empty list; empty list members are rejected. Existing raw queries, exclude and filter
codecs are not globally reinterpreted.

The binder also exposes source preparation separately from conversion. A mode-aware
adapter's `result_type_for(params)` reads prepared parameter presence without
consuming or converting values; the common runner carries that expected identity
through validation and error construction. `validate_request(params, args)` checks
operation-specific applicability before analysis.

Constructor-bound structure calls explicitly declare class-local
`BOUND_QUERY_CALL = True`. Surface is the initial adopter; Contracts and Trace also
adopt this protocol. Each actual
`get_structure(self)` takes no query keywords; canonical construction owns declared
controls, and the structure boundary bypasses signature-name forwarding for that
class. Subclasses declare adoption themselves, preserving unadopted custom plugin
`from_uri` behavior. Check and element dispatch retain their existing contracts.

For adopted `api.query` structure calls, the shared binder validates the original URI
query before applying explicit typed keyword overrides by canonical declaration name.
This includes required URI selectors: Trace still requires a valid URI `from` before
an override can replace it. API overrides use `from` (via dictionary expansion), while
plain constructor `params=` retains its CLI destination name `root`.
Unknown API keys raise `TypeError`; False, zero and empty values participate, and
None follows the declaration's default policy. Typed values validate once without
URI serialization or decoding. Fresh bound parameters preserve normalization and
non-consuming validation; actual reads establish use. Raw analysis leaves presentation
controls such as Surface's top unconsumed. Contracts preserves its existing read of
presentation impls during result assembly and records `impls_cap`; its implementation
arrays stay complete. Existing API resource splitting/decoding and host-request
scope remain unchanged. Other adapters retain method-keyword forwarding until qualified.

For qualified direct URI operations without declared parameter binding, an optional
adapter-owned `uri_result_type(resource)` resolves identity from the original resource
before construction, including validation and preparation failures. The fallback is
the adapter's `RESULT_TYPE`; AST mode extraction retains its existing query spelling
and duplicate-key behavior.

Required answer qualification runs before and after postprocessing. Generic trust
frames allow optional `meta.errors`/`meta.warnings`; present fields must be lists of
diagnostic dictionaries. Each warning requires a nonempty string `type`; unknown
warning kinds remain valid and `code` is optional. Error diagnostics retain an
optional string `type` and do not become fatal solely because they exist.
Repair preserves valid warnings and usable errors, records malformed warning
details in a bounded `invalid_adapter_warning` error, and records
`invalid_adapter_answer` as required failure. The original answer is not mutated.
An optional adapter-owned `answer_requirement_error(result, expected_type,
prior_facts=None)` returns a diagnostic or `None` after generic frame validation.
The postprocess call receives immutable established execution facts, so copied and
in-place transformations cannot hide previously required comparison proof. A pure
usage rejection before analysis can legitimately lack that proof. Final field
selection happens afterward and retains the established analysis facts.

Adapters that opt into the existing-path-first resource codec, including Surface
and Overview (and its architecture alias), preserve an existing literal path first. If it does not
exist, a once-decoded existing path can resolve URI-escaped characters. If both paths
exist, the literal path wins. The resolved path and raw query remain separate through
validation, exclusions and construction, so a decoded question mark never becomes a
new query delimiter. Bound Python API URI calls apply the same codec after query
validation; legacy factories without typed overrides keep their existing path policy.
Invalid encoded UTF-8/NUL rejects the resource; permission/I/O
failure is operational failure, never permission to select another path.

---

## Reserved Field Names

The following field names are reserved and MUST NOT be used for adapter-specific data:

- `contract_version`
- `type`
- `source`
- `source_type`
- `meta` (v1.1+)
- `metadata`
- `query`
- `next_steps`
- `status`
- `issues`
- `error`: only for a failed result (see [Outcomes](#outcomes-failed-not-applicable-truncated-ok))
- `version` (use `contract_version` instead)

---

## Naming Conventions

### Type Field Values

**Format**: `snake_case` (lowercase with underscores)

```python
# ✅ Correct
"ast_query"
"mysql_server"
"environment"
"python_structure"

# ❌ Incorrect
"ast-query"        # No hyphens
"AstQuery"         # No camelCase
"AST_QUERY"        # No uppercase
```

### Line Number Fields

For elements with source locations, use:
- `line_start` (int) - First line (1-indexed)
- `line_end` (int) - Last line (1-indexed, inclusive)

```python
# ✅ Correct
{
    'name': 'my_function',
    'line_start': 42,
    'line_end': 56
}

# ❌ Incorrect
{
    'name': 'my_function',
    'line': 42,         # Ambiguous
    'end': 56           # Not namespaced
}
```

---

## Validation Rules

### V023: Output Contract Compliance

Adapters MUST comply with the Output Contract specification.

**Checks**:
1. ✅ Required fields present (`contract_version`, `type`, `source`, `source_type`)
2. ✅ Type field uses snake_case format
3. ✅ Line fields use `line_start`/`line_end` (not `line`)
4. ✅ No conflicts with reserved field names

**Command**:
```bash
reveal check reveal/adapters/myadapter.py
```

**Implementation**: See `reveal/rules/validation/V023.py`

For shared adapter seams, run:

```bash
reveal reveal:// --check --select V023,V033,V034,V035
reveal reveal:// --check --format json
```

V023 also probes the live builder: payloads cannot replace envelope fields, and
supplied diagnostics must survive. `ResultBuilder.create()` accepts explicit
`scope=` and `meta=` fields; `data=` is reserved for the adapter payload. Trust
metadata arguments upgrade a legacy 1.0 result to the current contract so they
are preserved. An explicit `meta=` block cannot be combined with those arguments.
V033 checks returned/raised composition failures, confidence and consumption;
V034 rejects invalid/negative pagination controls and verifies zero/boundaries;
V035 checks text/JSON diagnostics, truncation disclosure and failure exits using
a recorded offline stats fixture plus the shared URI outcome seam.

Check results include rule execution coverage (`run`, `skipped`, `unavailable`,
`failed`, and reasons). Rules retain their detection-list interface and report
prerequisite outcomes through `BaseRule.unavailable()` or scope exclusions through
`not_applicable()`. Multi-subject probes record `completed(subject)` and preserve
subject details under one ledger entry per rule. An unavailable prerequisite, rule
crash or no applicable checks makes the run incomplete. Findings and incomplete
runs exit 1; a clean completed run exits 0. Ordinary target/config exclusions are
skips, not unavailable checks. V035 remains a bounded renderer canary.

`reveal check <file|dir>` carries the same ledger as `coverage` (`rules.coverage_report`, one
renderer): each rule once, with `files` = how many files it ran on, was not applicable to
(`skipped`), could not inspect (`unavailable`) or crashed on, its deduplicated `reason`, and
`subjects` for items inside a file that were skipped. A rule never looked at a file that has no
ledger (no analyzer, generated, lost with a pool worker), so it is not counted as having run on
it. Text prints one `Checks:` block before the summary: a rule unavailable on any file always
prints; rules not applicable to some files print only under `--select` (the default view would add
~50 "target does not match" lines for rules aimed at other targets); JSON carries every rule. The
block changes no exit code: unlike the `reveal://` self-check, an unavailable rule on a plain
`check` does not make the run incomplete.



---

## Versioning Strategy

### Contract Version Evolution

| Change Type | Version Bump | Example |
|-------------|--------------|---------|
| Add optional field | Patch (1.0 → 1.1) | Add `metadata.timestamp` |
| Change optional field | Minor (1.0 → 1.5) | Rename recommended field |
| Change required field | Major (1.0 → 2.0) | Rename `source` to `origin` |
| Remove required field | Major (1.0 → 2.0) | Remove `type` field |

### Backwards Compatibility

#### Phase 1: Additive (v1.0 - Current)
- **Add** contract fields to all adapters
- **Keep** legacy fields for compatibility
- **Emit** deprecation warnings via V023

Example output (transitional):
```python
{
    'contract_version': '1.0',
    'type': 'ast_query',
    'source': 'src/main.py',
    'source_type': 'file',
    'path': 'src/main.py',      # DEPRECATED: Use 'source' instead
    'results': [...]
}
```

#### Phase 2: Hard Migration (v2.0 - Future)
- **Remove** deprecated fields
- **Enforce** contract compliance strictly
- **Break** compatibility with pre-v1.0 consumers

---

## Migration Checklist

For adapter/analyzer authors migrating to v1.0:

### Step 1: Add Required Fields
```python
def get_structure(self, **kwargs):
    return {
        'contract_version': '1.0',           # ← Add this
        'type': 'my_adapter_type',           # ← Add/update this
        'source': self.source_path,          # ← Add this
        'source_type': 'file',               # ← Add this
        # ... rest of output
    }
```

### Step 2: Standardize Type Naming
```python
# Before
'type': 'my-adapter'

# After
'type': 'my_adapter'
```

### Step 3: Migrate Line Fields
```python
# Before
{
    'name': 'foo',
    'line': 42,
    'line_count': 10
}

# After
{
    'name': 'foo',
    'line_start': 42,
    'line_end': 51      # 42 + 10 - 1
}
```

### Step 4: Add Validation Tests
```python
def test_output_contract_compliance(self):
    """Verify adapter output conforms to v1.0 contract."""
    adapter = MyAdapter('test.py')
    result = adapter.get_structure()

    # Required fields
    assert 'contract_version' in result
    assert 'type' in result
    assert 'source' in result
    assert 'source_type' in result

    # Type naming
    assert re.match(r'^[a-z][a-z0-9_]*$', result['type'])

    # Source type
    assert result['source_type'] in ['file', 'directory', 'database', 'runtime', 'network']
```

---

## Checking Contract Compliance

Use the V023 rule to check adapter output compliance:

```bash
# Check a specific adapter implementation for contract compliance
reveal check reveal/adapters/myadapter.py --select V023

# Check all adapters at once
reveal check reveal/adapters/ --select V023
```

---

## Examples

### Minimal Compliant Output

```python
{
    'contract_version': '1.0',
    'type': 'file_structure',
    'source': 'src/main.py',
    'source_type': 'file'
}
```

### Full-Featured Output

```python
{
    'contract_version': '1.0',
    'type': 'ast_query',
    'source': 'src/api/',
    'source_type': 'directory',
    'metadata': {
        'total_files': 12,
        'total_results': 47,
        'timestamp': '2026-01-17T14:30:00Z',
        'duration_ms': 123
    },
    'query': {
        'complexity': {'op': '>', 'value': 5},
        'type': 'function'
    },
    'results': [
        {
            'file': 'src/api/auth.py',
            'name': 'authenticate',
            'type': 'function',
            'line_start': 42,
            'line_end': 67,
            'complexity': 8,
            'signature': 'def authenticate(username, password)'
        }
    ],
    'next_steps': [
        'reveal ast://src/api/auth.py:authenticate',
        'reveal stats://src/api/ --hotspots'
    ],
    'status': {
        'health': 'warning',
        'warnings': ['High complexity function found'],
        'errors': []
    }
}
```

---

## Implementation Status

Run `reveal check reveal/adapters/ --select V023` for a live compliance report. The static table that used to live here became stale faster than it could be maintained and was removed.

Element results (`env://HOME`, `python://packages`, `reveal 'reveal://<file>' <element>`) carry the envelope too: the router fills in `contract_version`, `type` (the adapter's `ELEMENT_RESULT_TYPE`, else `<scheme>_element`), `source` and `source_type` around the adapter's own fields, which win. The directory and `--files` views answer `directory_tree` / `file_list` (BACK-1591).

---

## FAQ

**Q: Why 4 required fields? Isn't that too rigid?**

A: 4 fields is the minimum needed for:
- Version tracking (`contract_version`)
- Schema identification (`type`)
- Data provenance (`source`)
- Source categorization (`source_type`)

Everything else is optional, allowing flexibility.

**Q: Can I add my own fields?**

A: Yes! Add any fields you need, just avoid reserved names. Put domain-specific data at the top level, generic metadata in `metadata`.

**Q: What if my adapter doesn't have a "source"?**

A: Every adapter has a source:
- Files: path
- Databases: connection string
- Runtime: `"env://"`, `"python://runtime"`
- Network: URL

**Q: Do I need to migrate immediately?**

A: No. V023 will emit warnings but not fail builds. You have until v2.0 (12+ months) to migrate.

**Q: How do I test contract compliance?**

A: Use the validation utilities:
```python
from reveal.contracts import validate_output
validate_output(result, version='1.0')
```

Or run V023 validation:
```bash
reveal check reveal/adapters/myadapter.py --select V023
```

---

## References

- **Validation**: `reveal/rules/validation/V023.py` - Contract enforcement
- **Adapter Guide**: `development/ADAPTER_AUTHORING_GUIDE.md` - Creating adapters

---

**Status**: This is a living document. Feedback welcome via GitHub issues.

**Next Steps**:
1. Implement V023 validation rule
2. Migrate 3-5 core adapters to v1.0
3. Add `reveal schema` command
4. Update adapter authoring guide
5. Release v0.38.0 with Output Contract support

## See Also

- [CONFIGURATION_GUIDE.md](../guides/CONFIGURATION_GUIDE.md) - Configuring output format and rules
- [QUICK_START.md](../QUICK_START.md) - Getting started with reveal
