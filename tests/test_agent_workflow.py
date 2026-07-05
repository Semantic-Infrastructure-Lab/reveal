"""BACK-434 — agent workflow validation.

reveal's product thesis is agent-readable progressive disclosure: an agent with
no hardcoded knowledge of reveal's URI syntax should be able to *discover* the
right surface (`--agent-help` -> `help://quick` / `--discover` / `help://schemas`)
and turn that discovery into commands that actually *execute*.

Every other test suite proves reveal's analysis is correct (conformance matrix,
test_smoke_tier). This suite proves a different, orthogonal thing: that the
discovery layer is *honest* — that the schemas reveal advertises to agents
compose into valid, runnable commands, not just plausible-looking text. That is
the failure class BACK-429 was (semantic output fine, the advertised JSON path
crashed because an internal node object leaked through one branch): a promise
that does not compose into a working command.

Assertions here are structural/executability, not exact output — the schema is
allowed to evolve. What is *not* allowed: an advertised discovery path that
tracebacks, returns invalid JSON, or names an analyzer/capability the following
commands don't actually support.
"""

import json
import re
from pathlib import Path

import pytest
from conftest import _run_reveal_direct

from reveal.adapters.base import _ADAPTER_REGISTRY

# A real, analyzed fixture to build discovered queries against. Reused from the
# conformance matrix so this suite doesn't own a parallel fixture to maintain.
CONFORMANCE_DIR = Path(__file__).parent / "fixtures" / "conformance" / "python"
FIXTURE_FILE = CONFORMANCE_DIR / "sample.py"

# The core code-understanding adapters an agent is routed to first. Each must be
# discoverable AND its schema must compose into an executable, JSON-returning
# command. Query built per-adapter from the schema's own advertised surface.
CORE_ADAPTERS = ("ast", "calls", "imports", "stats", "git", "diff", "help")

# Every publicly-registered adapter, read live from the registry rather than
# hardcoded — so a newly-added adapter is swept automatically instead of
# silently sitting outside test_schema_is_valid_and_names_itself /
# test_schema_example_queries_are_well_formed the way 17 of 24 adapters did
# before this list existed (found auditing the discovery contract, see
# internal-docs/research/REVEAL_GOALS_PRIORITY_ASSESSMENT_2026-07-05.md).
ALL_PUBLIC_ADAPTERS = tuple(sorted(
    name for name, cls in _ADAPTER_REGISTRY.items()
    if not getattr(cls, "internal", False)
))

# The query adapters an agent builds URIs against. `help` is excluded: it is a
# discovery meta-adapter that lists other adapters' schemas, so it correctly
# advertises no example queries of its own scheme.
QUERY_ADAPTERS = ("ast", "calls", "imports", "stats", "git", "diff")


def _run(*args):
    return _run_reveal_direct(*args)


def _assert_sane(result, desc):
    assert result.returncode in (0, 1), (
        f"{desc}: unexpected crash (rc={result.returncode}): {result.stderr}"
    )
    assert "Traceback (most recent call last)" not in result.stderr, (
        f"{desc}: unhandled exception:\n{result.stderr}"
    )


# --------------------------------------------------------------------------- #
# Layer 0: the discovery entry points exist and route to each other
# --------------------------------------------------------------------------- #

def test_agent_help_routes_to_discovery():
    """`--agent-help` is the front door — it must point agents onward to the
    machine-readable discovery surfaces, not dead-end in prose."""
    result = _run("--agent-help")
    _assert_sane(result, "--agent-help")
    out = result.stdout
    for pointer in ("help://quick", "--discover", "help://schemas"):
        assert pointer in out, (
            f"--agent-help does not route agents to {pointer!r}; discovery chain "
            f"is broken at the entry point"
        )


def test_discover_is_valid_json_and_self_consistent():
    """`--discover --format=json` is the one-call registry dump. It must be valid
    JSON and internally consistent (advertised count == actual adapters)."""
    result = _run("--discover", "--format=json")
    _assert_sane(result, "--discover --format=json")
    data = json.loads(result.stdout)  # must be valid JSON, not a crash dump
    assert data["adapter_count"] == len(data["adapters"]), (
        f"--discover advertises {data['adapter_count']} adapters but the registry "
        f"dump contains {len(data['adapters'])} — the count agents trust is wrong"
    )
    for adapter in CORE_ADAPTERS:
        assert adapter in data["adapters"], (
            f"core code-understanding adapter {adapter!r} missing from --discover"
        )


def test_discover_entries_conform_to_the_discovery_api_shape():
    """BACK-453 — `--discover` is a *different, coarser* contract from raw
    `get_schema()` / `help://schemas/<a>`: agents consume the registry dump to
    pick an adapter, then drill into a schema for detail. That dump layer had no
    shape guard — only the raw-schema layer did (`test_..._names_itself` above).

    Every `--discover` entry must expose the uniform discovery-API shape below,
    and self-name via `scheme` (the dump's equivalent of a raw schema's
    `adapter` key). A future adapter that drops `query_params`, renames `scheme`,
    or degrades to a stub (the `help://` "Schema not available" bug, BACK-473)
    should fail here rather than silently break agent discovery."""
    result = _run("--discover", "--format=json")
    _assert_sane(result, "--discover --format=json")
    data = json.loads(result.stdout)

    # The discovery-API entry contract. Distinct from a raw schema (which names
    # itself `adapter` and carries `elements`/`operators`/`type`): the dump is
    # normalized down to exactly these keys for every advertised adapter.
    DISCOVERY_ENTRY_KEYS = {
        "scheme", "description", "uri_syntax", "output_types", "query_params",
        "cli_flags", "cli_only_flags", "supports_batch", "supports_advanced",
        "example_queries", "notes",
    }
    for scheme, entry in data["adapters"].items():
        assert set(entry.keys()) == DISCOVERY_ENTRY_KEYS, (
            f"--discover entry {scheme!r} shape drifted: "
            f"missing {DISCOVERY_ENTRY_KEYS - set(entry)}, "
            f"extra {set(entry) - DISCOVERY_ENTRY_KEYS}"
        )
        assert entry["scheme"] == scheme, (
            f"--discover entry keyed {scheme!r} self-names as {entry['scheme']!r}"
        )
        # Honesty: no advertised adapter may dump as a schema-less stub — even a
        # meta-adapter like help:// describes itself via get_help() (BACK-473).
        assert entry["description"] and entry["description"] != "Schema not available", (
            f"--discover entry {scheme!r} has no honest description "
            f"({entry['description']!r}) — reads as broken to a discovering agent"
        )
        # The dump's example URIs are the ones an agent copy-pastes first; they
        # must be bare `scheme://...` URIs, not CLI lines or pipelines (BACK-471).
        for uri in entry["example_queries"]:
            assert isinstance(uri, str) and "://" in uri and not uri.startswith("reveal "), (
                f"--discover entry {scheme!r} has a malformed example URI: {uri!r}"
            )


def test_mcp_server_docstrings_have_no_stale_adapter_count():
    """BACK-472 — the MCP tool metadata agents read to decide *how* to call a
    tool is a discovery surface too, same as --discover/help://schemas. A
    hardcoded "N adapters" in a docstring drifts the moment an adapter is
    added or removed (this is exactly the BACK-471 doc-drift failure class,
    found here instead of in a public .md file), so no digit is allowed in
    that phrasing at all — not even one that happens to match today's count."""
    mcp_server = Path(__file__).parent.parent / "reveal" / "mcp_server.py"
    source = mcp_server.read_text()
    match = re.search(r"any of (\d+) adapters", source)
    assert match is None, (
        f"mcp_server.py hardcodes an adapter count ({match.group(1)!r}) in a "
        "tool docstring agents read — it will drift as adapters are added/removed"
    )


# --------------------------------------------------------------------------- #
# Layer 1: each core adapter's schema is shaped for an agent to build a query
# --------------------------------------------------------------------------- #

@pytest.fixture(params=CORE_ADAPTERS)
def adapter(request):
    return request.param


def _schema(adapter):
    result = _run(f"help://schemas/{adapter}", "--format=json")
    _assert_sane(result, f"help://schemas/{adapter}")
    return json.loads(result.stdout)


def test_schema_is_valid_and_names_itself(adapter):
    """Every core adapter must have a machine-readable schema that identifies
    itself — this is what `--discover` and `help://schemas/<a>` promise agents."""
    schema = _schema(adapter)
    assert schema.get("adapter") == adapter, (
        f"help://schemas/{adapter} identifies as {schema.get('adapter')!r}"
    )


@pytest.mark.parametrize("adapter", QUERY_ADAPTERS)
def test_schema_example_queries_are_well_formed(adapter):
    """Advertised example queries must actually be for this adapter (uri starts
    with `<adapter>://`) — an agent copies these verbatim as a starting point."""
    schema = _schema(adapter)
    examples = schema.get("example_queries", [])
    assert examples, f"{adapter} schema advertises no example_queries for agents"
    for ex in examples:
        assert "uri" in ex, f"{adapter} example query missing 'uri': {ex}"
        assert ex["uri"].startswith(f"{adapter}://"), (
            f"{adapter} example query uri {ex['uri']!r} is not a {adapter}:// URI — "
            f"an agent building on it would target the wrong adapter"
        )


# --------------------------------------------------------------------------- #
# Layer 1b: the same two checks, swept across every public adapter — not just
# the 7 "core" ones above. CORE_ADAPTERS/QUERY_ADAPTERS are spot-checks with
# deeper executability tests (Layer 2); this sweep is the full-registry floor
# every public adapter must clear, cheap enough to run for all of them since it
# only inspects the schema dict, no real backend/network/DB state required.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("adapter", ALL_PUBLIC_ADAPTERS)
def test_every_public_adapter_schema_is_valid_and_names_itself(adapter):
    """Same contract as test_schema_is_valid_and_names_itself, for every
    registered public adapter — a schema that mis-names itself or tracebacks
    breaks --discover/help://schemas silently for that one entry."""
    schema = _schema(adapter)
    assert schema.get("adapter") == adapter, (
        f"help://schemas/{adapter} identifies as {schema.get('adapter')!r}"
    )


# help:// is a discovery meta-adapter listing other adapters' schemas — it
# correctly advertises no example_queries of its own scheme (see QUERY_ADAPTERS
# comment above).
_ADAPTERS_WITH_EXAMPLES = tuple(a for a in ALL_PUBLIC_ADAPTERS if a != "help")


@pytest.mark.parametrize("adapter", _ADAPTERS_WITH_EXAMPLES)
def test_every_public_adapter_example_queries_are_well_formed(adapter):
    """Same contract as test_schema_example_queries_are_well_formed, for every
    registered public adapter. Catches the class of bug found in autossl/cpanel/
    letsencrypt (BACK-432/agent-contract audit, 2026-07-05): 'uri' fields that
    were actually full CLI invocations (`'reveal cpanel://x --flag'`) or shell
    pipelines, not parseable URIs — an agent treating them as a URI would break."""
    schema = _schema(adapter)
    examples = schema.get("example_queries", [])
    assert examples, f"{adapter} schema advertises no example_queries for agents"
    for ex in examples:
        assert "uri" in ex, f"{adapter} example query missing 'uri': {ex}"
        assert ex["uri"].startswith(f"{adapter}://"), (
            f"{adapter} example query uri {ex['uri']!r} is not a bare {adapter}:// "
            f"URI — an agent building on it would get a malformed query or target "
            f"the wrong adapter"
        )


# --------------------------------------------------------------------------- #
# Layer 2: the heart — a query built from the schema actually executes
# --------------------------------------------------------------------------- #

# One concrete query per code adapter, constructed only from surface the schema
# advertises (scheme + a documented query param), pointed at a real fixture.
# This is the "discovery composes into a valid command" proof.
_EXECUTABLE_QUERY = {
    "ast": lambda: f"ast://{CONFORMANCE_DIR}?type=function",
    "calls": lambda: f"calls://{FIXTURE_FILE}?target=process_order",
    "imports": lambda: f"imports://{FIXTURE_FILE}",
    "stats": lambda: f"stats://{CONFORMANCE_DIR}",
}


@pytest.mark.parametrize("adapter", sorted(_EXECUTABLE_QUERY))
def test_schema_built_query_executes_and_returns_json(adapter):
    """The failure class BACK-434 exists to catch: an advertised query shape that
    an agent builds from the schema but that tracebacks or emits invalid JSON.
    Build the query from the adapter's own advertised scheme+param, run it against
    a real fixture, and require valid JSON out."""
    uri = _EXECUTABLE_QUERY[adapter]()
    result = _run(uri, "--format", "json")
    _assert_sane(result, f"{adapter} discovered query {uri!r}")
    assert result.stdout.strip(), f"{adapter}: discovered query produced no output"
    json.loads(result.stdout)  # BACK-429 shape: must not leak a crash / non-JSON


# --------------------------------------------------------------------------- #
# Layer 3: capabilities/explain-file are honest about what follows
# --------------------------------------------------------------------------- #

def test_capabilities_advertises_extractable_elements_that_extract():
    """`--capabilities <file>` tells an agent what it can pull from a file. Those
    promises must hold: an advertised extractable element type must correspond to
    a real element the drill-down command (`reveal <file> <element>`) can extract."""
    result = _run("--capabilities", str(FIXTURE_FILE))
    _assert_sane(result, "--capabilities")
    caps = json.loads(result.stdout)
    assert caps["exists"] is True
    assert caps["analyzer"]["type"] == "explicit", (
        "python fixture should get a full explicit analyzer, not fallback"
    )
    assert "function" in caps["extractable"]["types"], (
        "--capabilities does not advertise functions as extractable for a .py file"
    )

    # Derive a real function name from --outline (not hardcoded), then prove the
    # advertised drill-down actually extracts it.
    outline = _run(str(FIXTURE_FILE), "--outline")
    _assert_sane(outline, "--outline")
    assert "process_order" in outline.stdout, "fixture drifted; expected process_order"
    extracted = _run(str(FIXTURE_FILE), "process_order")
    _assert_sane(extracted, "reveal <file> process_order")
    assert "process_order" in extracted.stdout, (
        "--capabilities advertised function extraction but `reveal <file> "
        "process_order` did not return the function body"
    )


def test_explain_file_agrees_with_capabilities():
    """`--explain-file` (human) and `--capabilities` (machine) must name the same
    analyzer — an agent that reads one and a human that reads the other should not
    get different answers about how a file is analyzed."""
    caps = json.loads(_run("--capabilities", str(FIXTURE_FILE)).stdout)
    explain = _run("--explain-file", str(FIXTURE_FILE))
    _assert_sane(explain, "--explain-file")
    analyzer_name = caps["analyzer"]["name"]  # e.g. "Python"
    assert analyzer_name in explain.stdout, (
        f"--explain-file does not name the {analyzer_name!r} analyzer that "
        f"--capabilities reports"
    )
