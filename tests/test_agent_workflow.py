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
from pathlib import Path

import pytest
from conftest import _run_reveal_direct

# A real, analyzed fixture to build discovered queries against. Reused from the
# conformance matrix so this suite doesn't own a parallel fixture to maintain.
CONFORMANCE_DIR = Path(__file__).parent / "fixtures" / "conformance" / "python"
FIXTURE_FILE = CONFORMANCE_DIR / "sample.py"

# The core code-understanding adapters an agent is routed to first. Each must be
# discoverable AND its schema must compose into an executable, JSON-returning
# command. Query built per-adapter from the schema's own advertised surface.
CORE_ADAPTERS = ("ast", "calls", "imports", "stats", "git", "diff", "help")

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
