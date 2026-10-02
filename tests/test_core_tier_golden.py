"""Core-five tier: golden text output and text/JSON parity (BACK-1601).

Five operations carry about 90% of real reveal use: extract an element, extract
a markdown section, ``--grep``, outline a file, read a line range. Their text
output is what agents read, so it is pinned here byte for byte, across the 13
tier-1 languages (the ``tests/fixtures/conformance`` samples) plus markdown.

Each golden file is a transcript: every command, its stdout, its stderr when
there is any, and its exit code. A diff is a change agents will see. To accept
an intended change, regenerate and review the diff like code::

    REVEAL_UPDATE_GOLDEN=1 pytest tests/test_core_tier_golden.py -n0

Views pinned:
- plain: what an agent gets by default. stdout is not a TTY, so breadcrumbs
  are off.
- crumbs-cold / crumbs-warm: breadcrumbs forced on in config. Cold is a first
  run (every show-once hint prints); warm is every later run, which is what a
  long-lived agent install sees.

The parity tests check that ``--format json`` carries the same items as the
text view for each operation, so neither view can drop something silently.
"""

import difflib
import json
import os
import re
import shlex
from pathlib import Path

import pytest
import yaml

from conftest import _run_reveal_direct

pytestmark = pytest.mark.conformance

TESTS_DIR = Path(__file__).parent
CONFORMANCE_DIR = TESTS_DIR / "fixtures" / "conformance"
CORE_DIR = TESTS_DIR / "fixtures" / "core_tier"
GOLDEN_DIR = CORE_DIR / "golden"
UPDATE = os.environ.get("REVEAL_UPDATE_GOLDEN") == "1"

EXPECTED = yaml.safe_load((CONFORMANCE_DIR / "expected.yaml").read_text(encoding="utf-8"))
LANGUAGES = sorted(EXPECTED)
EXTENSIONS = {
    "python": "py", "c": "c", "cpp": "cpp", "csharp": "cs", "go": "go",
    "java": "java", "javascript": "js", "rust": "rs", "typescript": "ts",
    "kotlin": "kt", "swift": "swift", "ruby": "rb", "php": "php",
}

DOC = "guide.md"
DOC_SECTIONS = ["Setup", "Fixed", "2026", "Known gaps", "Order Service Guide"]


def _sample(lang: str) -> str:
    return f"{lang}/sample.{EXTENSIONS[lang]}"


def _language_commands(lang: str) -> list:
    """The five operations on one tier-1 sample, as argv lists."""
    exp = EXPECTED[lang]
    path = _sample(lang)
    call_line = exp["calls_validate_callers"][0]["line"]
    return [
        [path],
        [path, "--outline"],
        [path, exp["entry_function"]],
        [path, exp["batch_element"]],
        [path, f":{call_line}-{call_line + 2}"],
        [path, f":{call_line}"],
        [path, "--grep", "result"],
    ]


def _doc_commands() -> list:
    return [
        [DOC],
        [DOC, "--outline"],
        *[[DOC, name] for name in DOC_SECTIONS],
        [DOC, "--section", "Usage"],
        [DOC, ":9-13"],
        [DOC, "--grep", "order"],
        # --head/--tail/--range count an extracted section's lines (BACK-1626)
        [DOC, "Order Service Guide", "--head", "5"],
        [DOC, "Setup", "--tail", "4"],
        [DOC, "Requirements|Batching", "--head", "6"],
        [DOC, "Usage", "--range", "50-60"],
    ]


# ── isolated runs ────────────────────────────────────────────────────────────

class _Runner:
    """Runs reveal in-process with nothing from the developer's machine leaking in.

    No user or project config, no disk cache, and a private XDG data dir, which
    holds the show-once hint state. ``crumbs`` turns breadcrumbs on through a
    REVEAL_CONFIG file (REVEAL_NO_CONFIG would also drop REVEAL_BREADCRUMBS).
    """

    def __init__(self, tmp_path: Path, monkeypatch):
        self.tmp = tmp_path
        self.mp = monkeypatch
        for key in list(os.environ):
            if key.startswith("REVEAL_") and key != "REVEAL_MAX_WORKERS":
                monkeypatch.delenv(key)
        # XDG_CACHE_HOME stays: it holds the downloaded tree-sitter grammars.
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg_config"))
        monkeypatch.setenv("REVEAL_DISK_CACHE", "0")
        self.crumbs_config = tmp_path / "crumbs.yaml"
        self.crumbs_config.write_text("display:\n  breadcrumbs: true\n", encoding="utf-8")
        self.fresh_hint_state()

    def fresh_hint_state(self):
        data = self.tmp / f"xdg_data_{len(list(self.tmp.glob('xdg_data_*')))}"
        data.mkdir()
        self.mp.setenv("XDG_DATA_HOME", str(data))

    def run(self, cwd: Path, argv: list, *, crumbs: bool = False):
        from reveal import config as reveal_config
        if crumbs:
            self.mp.delenv("REVEAL_NO_CONFIG", raising=False)
            self.mp.setenv("REVEAL_CONFIG", str(self.crumbs_config))
        else:
            self.mp.delenv("REVEAL_CONFIG", raising=False)
            self.mp.setenv("REVEAL_NO_CONFIG", "1")
        saved = os.getcwd()
        os.chdir(cwd)
        reveal_config.RevealConfig._cache.clear()
        reveal_config._config = None
        try:
            return _run_reveal_direct(*argv)
        finally:
            os.chdir(saved)
            reveal_config.RevealConfig._cache.clear()
            reveal_config._config = None

    def json(self, cwd: Path, argv: list):
        result = self.run(cwd, [*argv, "--format", "json"])
        assert result.returncode == 0, f"reveal {' '.join(argv)} --format json: {result.stderr}"
        return json.loads(result.stdout)


@pytest.fixture
def runner(tmp_path, monkeypatch):
    return _Runner(tmp_path, monkeypatch)


# ── golden transcripts ───────────────────────────────────────────────────────

def _transcript(runner: _Runner, cwd: Path, commands: list, view: str) -> str:
    crumbs = view != "plain"
    if view == "crumbs-warm":
        for argv in commands:
            runner.run(cwd, argv, crumbs=True)
    parts = []
    for argv in commands:
        if view == "crumbs-cold":
            runner.fresh_hint_state()
        result = runner.run(cwd, argv, crumbs=crumbs)
        block = f"$ reveal {' '.join(_quote(a) for a in argv)}\n{result.stdout}"
        if result.stderr:
            block += f"[stderr]\n{result.stderr}"
        parts.append(f"{block}[exit {result.returncode}]\n")
    return "\n".join(parts)


def _quote(arg: str) -> str:
    return shlex.quote(arg)


def _check_golden(name: str, actual: str):
    path = GOLDEN_DIR / f"{name}.txt"
    if UPDATE:
        path.write_text(actual, encoding="utf-8", newline="\n")
        return
    assert path.exists(), f"missing golden {path.name}: run with REVEAL_UPDATE_GOLDEN=1"
    expected = path.read_text(encoding="utf-8")
    if actual != expected:
        diff = "".join(difflib.unified_diff(
            expected.splitlines(keepends=True), actual.splitlines(keepends=True),
            fromfile=f"golden/{path.name}", tofile="actual"))
        pytest.fail(f"core-tier text output changed (accept with REVEAL_UPDATE_GOLDEN=1):\n{diff}")


@pytest.mark.parametrize("lang", LANGUAGES)
def test_language_golden(runner, lang):
    _check_golden(lang, _transcript(runner, CONFORMANCE_DIR, _language_commands(lang), "plain"))


def test_markdown_golden(runner):
    _check_golden("markdown", _transcript(runner, CORE_DIR, _doc_commands(), "plain"))


def test_outline_order_golden(runner):
    """Decorated and plain members list in line order in both outline views."""
    commands = [["ordering.py"], ["ordering.py", "--outline"],
                ["ordering.py", "Account", "--head", "4"], ["ordering.py", "Account", "--range", "2-3"],
                ["ordering.py", "Account", "--tail", "2", "--format", "grep"]]
    _check_golden("ordering", _transcript(runner, CORE_DIR, commands, "plain"))


def test_directory_grep_golden(runner):
    commands = [[".", "--grep", "= validate"], ["python", "--grep", "result"]]
    _check_golden("directory-grep", _transcript(runner, CONFORMANCE_DIR, commands, "plain"))


CRUMB_COMMANDS = {
    "python": (CONFORMANCE_DIR, [["python/sample.py"], ["python/sample.py", "--outline"],
                                 ["python/sample.py", "process_order"], ["python/sample.py", ":12-14"],
                                 ["python/sample.py", "--grep", "result"]]),
    "markdown": (CORE_DIR, [[DOC], [DOC, "--outline"], [DOC, "Setup"]]),
}


@pytest.mark.parametrize("view", ["crumbs-cold", "crumbs-warm"])
@pytest.mark.parametrize("kind", sorted(CRUMB_COMMANDS))
def test_breadcrumbs_golden(runner, kind, view):
    cwd, commands = CRUMB_COMMANDS[kind]
    _check_golden(f"{kind}.{view}", _transcript(runner, cwd, commands, view))


# ── text/JSON parity ─────────────────────────────────────────────────────────

_CATEGORY_RE = re.compile(r"^(\w[\w ]*) \((\d+)\):$")
_ITEM_RE = re.compile(r"^\s+:(\d+)\s+(.*)$")
_OUTLINE_LINE_RE = re.compile(r"\((?:[^():]+:|line )(\d+)[,)]")
_EXTRACT_HEADER_RE = re.compile(r"^(.+):(\d+)-(\d+) \| (.+)$")
_EXTRACT_BODY_RE = re.compile(r"^ *(\d+)(?:  (.*))?$")
# "  name()      lines 13, 14 … 24 (5 hits)"; a hit outside any element is "  line 4".
_GREP_HIT_RE = re.compile(r"^ {2,}(\d+): (.*)$")


def _text(runner, cwd, argv) -> str:
    result = runner.run(cwd, argv)
    assert result.returncode == 0, f"reveal {' '.join(argv)}: {result.stderr}"
    return result.stdout


def _structure_items(data: dict) -> dict:
    return {key: [item["line"] for item in items]
            for key, items in data["structure"].items() if isinstance(items, list) and items}


def _assert_structure_parity(text: str, data: dict):
    sections, current = {}, None
    for line in text.splitlines():
        if m := _CATEGORY_RE.match(line):
            current = m.group(1).lower().replace(" ", "_")
            sections[current] = {"count": int(m.group(2)), "lines": []}
        elif current and (m := _ITEM_RE.match(line)):
            sections[current]["lines"].append(int(m.group(1)))
    json_items = _structure_items(data)
    assert set(sections) == set(json_items), (sections, json_items)
    for key, lines in json_items.items():
        assert sections[key]["count"] == len(lines), key
        assert sections[key]["lines"] == lines, key


def _assert_outline_parity(text: str, data: dict):
    text_lines = sorted(int(n) for n in _OUTLINE_LINE_RE.findall(text))
    json_lines = sorted(line for lines in _structure_items(data).values() for line in lines)
    assert text_lines == json_lines


def _assert_extract_parity(text: str, data: dict):
    lines = text.splitlines()
    header = next(line for line in lines if _EXTRACT_HEADER_RE.match(line))
    _, start, end, name = _EXTRACT_HEADER_RE.match(header).groups()
    assert (int(start), int(end), name) == (data["line_start"], data["line_end"], data["name"])
    body = [m for line in lines[lines.index(header) + 1:] if (m := _EXTRACT_BODY_RE.match(line))]
    assert [int(m.group(1)) for m in body] == list(range(int(start), int(end) + 1))
    text_source = [m.group(2) or "" for m in body]
    json_source = data["source"].split("\n")
    if json_source and json_source[-1] == "" and len(json_source) == len(text_source) + 1:
        json_source.pop()
    assert text_source == [line.rstrip() if not line.strip() else line for line in json_source]


def _assert_cut_parity(text: str, data: dict):
    """A cut element: same lines as JSON, and the text footer is JSON's truncation message."""
    _assert_extract_parity(text, data)
    (warning,) = [w for w in data["meta"]["warnings"] if w["type"] == "truncated"]
    assert f"⚠ Truncated {warning['message']}" in text.splitlines()
    assert warning["shown"] == data["line_end"] - data["line_start"] + 1


def _assert_grep_groups(rows: list, groups: list):
    """Text rows and JSON groups name the same elements with the same hits: line and text."""
    assert len(rows) == len(groups), (rows, groups)
    for (label, hits), group in zip(rows, groups):
        assert (group["name"] or "") in label, (label, group)
        assert hits == [(h["line"], h["text"]) for h in group["hits"]], (label, group)
        assert group["lines"] == [h["line"] for h in group["hits"]], group


def _grep_rows(block: str) -> list:
    """(label, [(line, text)]) per group: a 2-space label, then its "N: text" hit rows.

    A flat file has no labels: its hit rows form one unlabelled group.
    """
    rows: list = []
    for line in block.splitlines():
        if m := _GREP_HIT_RE.match(line):
            if not rows:
                rows.append(("", []))
            rows[-1][1].append((int(m.group(1)), m.group(2)))
        elif line.startswith("  ") and not line.startswith("   "):
            rows.append((line.strip(), []))
    return rows


def _assert_file_grep_parity(text: str, data: dict):
    assert f"{data['total_hits']} hit" in text.splitlines()[1]
    _assert_grep_groups(_grep_rows(text), data["groups"])


def _assert_dir_grep_parity(text: str, data: dict):
    blocks = re.split(r"^File: ", text, flags=re.M)[1:]
    assert len(blocks) == len(data["files"])
    for block, entry in zip(blocks, data["files"]):
        assert entry["path"].endswith(block.splitlines()[0].strip())
        _assert_grep_groups(_grep_rows(block), entry["groups"])


def _parity_cases(lang: str) -> list:
    exp = EXPECTED[lang]
    path = _sample(lang)
    call_line = exp["calls_validate_callers"][0]["line"]
    return [
        ([path], _assert_structure_parity),
        ([path, "--outline"], _assert_outline_parity),
        ([path, exp["entry_function"]], _assert_extract_parity),
        ([path, exp["batch_element"]], _assert_extract_parity),
        ([path, f":{call_line}-{call_line + 2}"], _assert_extract_parity),
        ([path, "--grep", "result"], _assert_file_grep_parity),
    ]


@pytest.mark.parametrize("lang", LANGUAGES)
def test_language_text_json_parity(runner, lang):
    for argv, check in _parity_cases(lang):
        check(_text(runner, CONFORMANCE_DIR, argv), runner.json(CONFORMANCE_DIR, argv))


@pytest.mark.parametrize("argv,check", [
    ([DOC], _assert_structure_parity),
    ([DOC, "--outline"], _assert_outline_parity),
    ([DOC, "Setup"], _assert_extract_parity),
    ([DOC, "2026"], _assert_extract_parity),
    ([DOC, "--section", "Usage"], _assert_extract_parity),
    ([DOC, ":9-13"], _assert_extract_parity),
    ([DOC, "--grep", "order"], _assert_file_grep_parity),
    (["ordering.py"], _assert_structure_parity),
    (["ordering.py", "--outline"], _assert_outline_parity),
    ([DOC, "Order Service Guide", "--head", "5"], _assert_cut_parity),
    (["ordering.py", "Account", "--range", "2-3"], _assert_cut_parity),
    (["ordering.py", "Account", "--tail", "3"], _assert_cut_parity),
], ids=lambda v: " ".join(v) if isinstance(v, list) else None)
def test_core_dir_text_json_parity(runner, argv, check):
    check(_text(runner, CORE_DIR, argv), runner.json(CORE_DIR, argv))


def test_directory_grep_text_json_parity(runner):
    argv = [".", "--grep", "= validate"]
    _assert_dir_grep_parity(_text(runner, CONFORMANCE_DIR, argv), runner.json(CONFORMANCE_DIR, argv))
