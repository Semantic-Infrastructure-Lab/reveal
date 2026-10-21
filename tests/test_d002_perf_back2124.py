"""BACK-2124: D002 does its per-pair work once per function and stops when the top
candidates are found, without changing a single detection.

Measured on python-celery (507 files, REVEAL_MAX_WORKERS=1, cold, contended box): D002 is
~24 s of a 29 s ``check --select D002``; ``SequenceMatcher.ratio()`` is 17.5 s of that,
``quick_ratio`` 2.7 s, the ``SequenceMatcher`` constructor (it builds the b2j index of its
second sequence) 2.2 s, ``_cosine_similarity`` 2.0 s, and vectorize/normalize/tokens
together 0.8 s. 142,592 matchers were built for 73,713 pairs and ``ratio()`` ran 47,723 times,
although a file reports at most ``MAX_CANDIDATES`` pairs.

The counts below are the deterministic evidence (wall time is not asserted):

* a matcher (b2j index) is built once per function, not once per pair;
* pairs are tried in descending interestingness and the sequence test stops at the
  ``MAX_CANDIDATES``-th pass; the reported list is the same as testing every pair;
* the cosine magnitude of a vector is computed once per function.

Equality is proven against ``_exhaustive``, a self-contained copy of the old algorithm
(every pair, fresh matcher per pair, sort, cap), on Python, Ruby and Lua fixtures. Ruby and Lua
have no signature terminator, so they also guard the rule against a Python-only assumption.
"""

import math
import re
import types
from difflib import SequenceMatcher

import pytest

import reveal.rules.duplicates.D002 as d002_module
from reveal.rules.duplicates._bodies import extract_function_body, is_trivial_hook_body
from reveal.rules.duplicates.D002 import D002

pytestmark = pytest.mark.component

# ---------------------------------------------------------------- fixtures

RUBY_TEMPLATE = [
    "def {n}(items, limit)",
    "  result = []",
    "  items.each do |item|",
    "    next if item.nil?",
    "    result << item.to_s.strip",
    "    break if result.size >= limit",
    "  end",
    '  label = "{t}"',
    "  log_result(result, label)",
    "  result",
    "end",
]
LUA_TEMPLATE = [
    "function {n}(items, limit)",
    "  local result = {{}}",
    "  for _, item in ipairs(items) do",
    "    if item ~= nil then",
    "      result[#result + 1] = tostring(item)",
    "    end",
    "    if #result >= limit then break end",
    "  end",
    '  local label = "{t}"',
    "  log_result(result, label)",
    "  return result",
    "end",
]
PYTHON_TEMPLATE = [
    "def {n}(items, limit):",
    "    result = []",
    "    for item in items:",
    "        if item is None:",
    "            continue",
    "        result.append(str(item).strip())",
    "        if len(result) >= limit:",
    "            break",
    '    label = "{t}"',
    "    log_result(result, label)",
    "    return result",
]
# Replaces body line k+1 of a template: unrelated identifiers, so each one lowers both the
# alpha-renamed and the literal token match of the pair.
JUNK = [
    "prepare_{n}_{k}(items, limit)",
    "audit_{n}_{k} = fetch_audit({k})",
    "notify_{n}_{k}(audit_{n}_{k}, limit)",
    "stash_{n}_{k}.push(limit, {k})",
    "flush_{n}_{k}(items)",
    "sync_{n}_{k}(items)",
    "mark_{n}_{k} = {k} * 7",
    "drop_{n}_{k}(items.first)",
]
TEMPLATES = {"ruby": RUBY_TEMPLATE, "lua": LUA_TEMPLATE, "python": PYTHON_TEMPLATE}
EXT = {"ruby": "rb", "lua": "lua", "python": "py"}


def _function_lines(lang, name, tag, junk=0):
    lines = [t.format(n=name, t=tag) for t in TEMPLATES[lang]]
    indent = len(lines[1]) - len(lines[1].lstrip())
    for k in range(junk):
        lines[1 + k] = " " * indent + JUNK[k].format(n=name, k=k)
    return lines


def _build(lang, specs):
    """(content, structure) for functions given as (name, tag[, junk]) or (name, lines)."""
    content_lines, functions = [], []
    for spec in specs:
        lines = spec[1] if isinstance(spec[1], list) else _function_lines(lang, *spec)
        start = len(content_lines) + 1
        content_lines.extend(lines)
        functions.append({"name": spec[0], "line": start, "line_end": len(content_lines)})
        content_lines.append("")
    return "\n".join(content_lines) + "\n", {"functions": functions}


def _exhaustive(rule, file_path, structure, content):
    """The pre-BACK-2124 algorithm, kept here as the oracle: vectors per function, every
    pair, a fresh SequenceMatcher per pair and per stage, stable sort, cap."""
    vectors = []
    for func in structure["functions"]:
        body = extract_function_body(func, content)
        if not body or len(body.strip()) < 20:
            continue
        line_count = len(body.split("\n"))
        if line_count < rule.MIN_FUNCTION_SIZE:
            continue
        normalized = rule._normalize(body)
        if is_trivial_hook_body(normalized):
            continue
        vectors.append((func, rule._vectorize(body), line_count, rule._tokens(normalized)))

    def ratio(a, b):
        return SequenceMatcher(None, a, b, autojunk=False).ratio()

    found = []
    for i in range(len(vectors)):
        for j in range(i + 1, len(vectors)):
            f1, v1, s1, t1 = vectors[i]
            f2, v2, s2, t2 = vectors[j]
            similarity = rule._cosine_similarity(v1, v2)
            if similarity < rule.MIN_SIMILARITY:
                continue
            if not (ratio(t1[0], t2[0]) >= rule.MIN_SEQUENCE_MATCH
                    or ratio(t1[1], t2[1]) >= rule.MIN_LITERAL_MATCH):
                continue
            found.append((similarity * math.sqrt(s1 + s2), similarity, s1 + s2, f1, f2))
    found.sort(reverse=True, key=lambda x: x[0])
    return [
        (f2.get("line", 0),
         f"{rule.message}: '{f2['name']}' ~{similarity:.0%} similar to '{f1['name']}' (line {f1.get('line', 0)})",
         f"Combined {size} lines. Worth investigating if logic can be shared.",
         f"Interestingness: {score:.1f} (similarity {similarity:.0%} × size {size})")
        for score, similarity, size, f1, f2 in found[:rule.MAX_CANDIDATES]
    ], len(found)


def _reported(rule, lang, structure, content):
    detections = rule.check(f"sample.{EXT[lang]}", structure, content)
    return [(d.line, d.message, d.suggestion, d.context) for d in detections]


@pytest.fixture
def counters(monkeypatch):
    """Count SequenceMatcher builds, ratio()/quick_ratio() calls and math.sqrt calls inside D002."""
    counts = {"built": 0, "ratio": 0, "quick": 0, "sqrt": 0}

    class Counting(SequenceMatcher):
        def __init__(self, *args, **kwargs):
            counts["built"] += 1
            super().__init__(*args, **kwargs)

        def ratio(self):
            counts["ratio"] += 1
            return super().ratio()

        def quick_ratio(self):
            counts["quick"] += 1
            return super().quick_ratio()

    def counting_sqrt(value):
        counts["sqrt"] += 1
        return math.sqrt(value)

    monkeypatch.setattr(d002_module, "SequenceMatcher", Counting)
    monkeypatch.setattr(d002_module, "math", types.SimpleNamespace(sqrt=counting_sqrt))
    return counts


# 12 near-copies: 66 pairs, every one passes cosine and the shaped match (only the label differs).
COPIES = [(f"copy_{k:02d}", f"tag{k}") for k in range(12)]
COPY_PAIRS = 12 * 11 // 2


# ---------------------------------------------------------------- red-first counts


class TestWorkIsDoneOncePerFunction:
    """Each fails on the per-pair code: it builds 66 matchers, runs 66 ratio()s and 198 sqrts."""

    @pytest.mark.parametrize("lang", ["ruby", "lua", "python"])
    def test_matcher_is_built_once_per_function(self, lang, counters):
        content, structure = _build(lang, COPIES)
        _reported(D002(), lang, structure, content)
        # One per function (shaped stage; the literal stage is only built when the shaped
        # one fails) -- not one per pair. Per-pair code builds COPY_PAIRS = 66.
        assert counters["built"] <= len(COPIES), counters

    @pytest.mark.parametrize("lang", ["ruby", "lua", "python"])
    def test_sequence_test_stops_at_the_cap(self, lang, counters):
        content, structure = _build(lang, COPIES)
        found = _reported(D002(), lang, structure, content)
        assert len(found) == D002.MAX_CANDIDATES
        # Every pair passes, so the 5th pass in rank order ends the work: 5 ratio() calls.
        # The exhaustive code runs one per pair (66).
        assert counters["ratio"] == D002.MAX_CANDIDATES, counters

    def test_tester_builds_one_matcher_per_function_for_every_pair(self, counters):
        """Same claim as above without the early exit hiding it: all 66 pairs are tested."""
        content, structure = _build("ruby", COPIES)
        rule = D002()
        tokens = [rule._tokens(rule._normalize(extract_function_body(f, content)))
                  for f in structure["functions"]]
        tester = d002_module._SequenceTester(rule, tokens)
        assert all(tester.is_match(i, j) for i in range(12) for j in range(i + 1, 12))
        assert counters["built"] == len(COPIES) - 1, counters  # every function but the first is a seq2
        assert counters["ratio"] == COPY_PAIRS, counters

    def test_cosine_magnitude_is_computed_once_per_function(self, counters):
        content, structure = _build("ruby", COPIES)
        _reported(D002(), "ruby", structure, content)
        # One sqrt per function for its magnitude plus one per scored pair for the
        # interestingness (the old code: 2 magnitudes + 1 interestingness per pair = 198).
        assert counters["sqrt"] <= len(COPIES) + COPY_PAIRS, counters


# ---------------------------------------------------------------- the cheap upper bounds

@pytest.mark.parametrize("lang", ["ruby", "lua"])
class TestUpperBoundsSkipRatio:
    """real_quick_ratio (2*min(la,lb)/(la+lb)) and quick_ratio (2*|multiset intersection|/(la+lb))
    are upper bounds of ratio(): matched blocks are a subset of the multiset intersection, which is
    no larger than the shorter sequence. A pair whose bound is under the floor cannot pass, so
    ratio() (17.5 of celery's 24 s) is not run. Both pairs clear the cosine floor, so only these
    bounds stand between them and a ratio() call. Measured:

      junk pair (a vs b with 8 body lines replaced), cosine / quick_ratio shaped / literal:
        ruby 0.631 / 0.440 / 0.242,  lua 0.671 / 0.495 / 0.323  (floors 0.5 / 0.7)
      length pair (b = a with its middle repeated 5x), cosine / real_quick_ratio:
        ruby 0.898 / 0.367,  lua 0.852 / 0.386  (floor 0.5; quick_ratio 0.358 / 0.376)
    """

    def test_multiset_bound_rejects_without_running_ratio(self, lang, counters):
        content, structure = _build(lang, [("a", "a", 0), ("b", "b", 8)])
        assert _reported(D002(), lang, structure, content) == []
        assert counters["ratio"] == 0, counters
        assert counters["quick"] == 2, counters  # shaped and literal stage

    def test_length_bound_rejects_before_the_multiset_bound(self, lang, counters):
        small = _function_lines(lang, "small", "s")
        big = _function_lines(lang, "big", "b")
        big = big[:2] + big[2:-2] * 5 + big[-2:]
        content, structure = _build(lang, [("small", small), ("big", big)])
        assert _reported(D002(), lang, structure, content) == []
        assert counters["quick"] == 0 and counters["ratio"] == 0, counters


# ---------------------------------------------------------------- output equality


def _ranked_failure_specs(lang):
    """A big pair that ranks first but is only skeleton-alike (low token match), plus small
    true copies: the early exit must test the big pair, reject it, and go on."""
    big_a = _function_lines(lang, "big_a", "a")
    big_b = _function_lines(lang, "big_b", "b", junk=8)
    indent = " " * (len(big_a[1]) - len(big_a[1].lstrip()))
    insert_at = len(big_a) - 2
    for k in range(40):
        big_a.insert(insert_at, f"{indent}pad_a_{k} = compute_a({k})")
        big_b.insert(insert_at, f"{indent}emit(row_{k}, scale_b * {k})")
    return [("big_a", big_a), ("big_b", big_b)] + [(f"small_{k}", f"s{k}") for k in range(4)]


FIXTURES = {}
for _lang in ("ruby", "lua", "python"):
    FIXTURES[f"{_lang}-ties"] = (_lang, [(n, t, 0) for n, t in COPIES])
    FIXTURES[f"{_lang}-ranked-failure"] = (_lang, _ranked_failure_specs(_lang))
    FIXTURES[f"{_lang}-mixed"] = (_lang, (
        [(f"fam_a{k}", f"a{k}", 0) for k in range(5)]
        + [(f"fam_b{k}", f"b{k}", 0 if k % 2 else 2) for k in range(5)]
        + [(f"far_{k}", f"f{k}", 8) for k in range(3)]
    ))


@pytest.mark.parametrize("fixture", sorted(FIXTURES))
def test_reports_exactly_what_testing_every_pair_reports(fixture):
    lang, specs = FIXTURES[fixture]
    content, structure = _build(lang, specs)
    rule = D002()
    expected, passing = _exhaustive(rule, "sample", structure, content)
    assert _reported(rule, lang, structure, content) == expected
    assert expected, f"{fixture}: nothing reported, the comparison would be vacuous"
    if fixture.endswith("ties"):
        # 66 passing pairs, 5 reported: the cap and the stable tie order are exercised.
        assert passing == COPY_PAIRS and len(expected) == D002.MAX_CANDIDATES


@pytest.mark.parametrize("lang", ["ruby", "lua", "python"])
def test_unrelated_pair_outranking_a_reported_pair_is_tried_and_rejected(lang):
    """Precondition of the ranked-failure fixtures: big_a/big_b pass the cosine floor and
    outrank the last reported pair by interestingness, so they are tested first, yet fail
    both sequence floors. Measured cosine: Ruby 0.501, Lua 0.512, Python 0.514."""
    content, structure = _build(lang, _ranked_failure_specs(lang))
    rule = D002()
    reported = _reported(rule, lang, structure, content)
    assert len(reported) == D002.MAX_CANDIDATES
    assert not any("'big_b'" in message and "'big_a'" in message for _, message, _, _ in reported)
    funcs = {f["name"]: f for f in structure["functions"]}
    body = {n: extract_function_body(f, content) for n, f in funcs.items()}
    cosine = rule._cosine_similarity(rule._vectorize(body["big_a"]), rule._vectorize(body["big_b"]))
    assert cosine >= rule.MIN_SIMILARITY, cosine
    big = cosine * math.sqrt(len(body["big_a"].split("\n")) + len(body["big_b"].split("\n")))
    last_reported = float(reported[-1][3].split()[1])
    assert big > last_reported, (big, last_reported)
    t_a, t_b = (rule._tokens(rule._normalize(body[n])) for n in ("big_a", "big_b"))
    assert not rule._is_sequence_match(t_a, t_b)


# ---------------------------------------------------------------- negative controls (Ruby, Lua)


# base vs var, where var replaces its first N body lines with unrelated statements.
# Measured (cosine / shaped match / literal match):
#   ruby N=2 0.969 / 0.449 / 0.742 reported by the literal rescue; N=3 0.916 / 0.292 / 0.607 not reported
#   lua  N=1 0.963 / 0.481 / 0.835 reported by the literal rescue; N=3 0.847 / 0.480 / 0.560 not reported
RESCUED = {"ruby": 2, "lua": 1}
UNDER_FLOORS = {"ruby": 3, "lua": 3}


@pytest.mark.parametrize("lang", ["ruby", "lua"])
class TestFloorsStillDecide:
    """Not Python: Ruby and Lua have no signature terminator, the shape the rule's body
    extraction has to survive. The pairs sit just either side of MIN_SEQUENCE_MATCH (0.5) and
    MIN_LITERAL_MATCH (0.7) while the cosine floor (0.5) is cleared, so the sequence stage alone decides."""

    def _pair(self, lang, junk):
        content, structure = _build(lang, [("base", "base", 0), ("var", "var", junk)])
        return _reported(D002(), lang, structure, content), structure, content

    def test_near_duplicate_is_reported(self, lang):
        found, _, _ = self._pair(lang, 0)
        assert len(found) == 1 and "'var' ~" in found[0][1] and "'base'" in found[0][1]

    def test_literal_rescue_pair_just_over_the_floor_is_reported(self, lang):
        found, structure, content = self._pair(lang, RESCUED[lang])
        rule = D002()
        b1, b2 = (rule._normalize(extract_function_body(f, content)) for f in structure["functions"])
        t1, t2 = rule._tokens(b1), rule._tokens(b2)
        ratio = lambda a, b: SequenceMatcher(None, a, b, autojunk=False).ratio()  # noqa: E731
        assert ratio(t1[0], t2[0]) < rule.MIN_SEQUENCE_MATCH
        assert ratio(t1[1], t2[1]) >= rule.MIN_LITERAL_MATCH
        assert len(found) == 1

    def test_pair_just_under_both_floors_is_not_reported(self, lang):
        found, structure, content = self._pair(lang, UNDER_FLOORS[lang])
        rule = D002()
        b1, b2 = (rule._normalize(extract_function_body(f, content)) for f in structure["functions"])
        t1, t2 = rule._tokens(b1), rule._tokens(b2)
        ratio = lambda a, b: SequenceMatcher(None, a, b, autojunk=False).ratio()  # noqa: E731
        assert ratio(t1[0], t2[0]) < rule.MIN_SEQUENCE_MATCH
        assert ratio(t1[1], t2[1]) < rule.MIN_LITERAL_MATCH
        vec = [rule._vectorize(extract_function_body(f, content)) for f in structure["functions"]]
        assert rule._cosine_similarity(*vec) >= rule.MIN_SIMILARITY  # the sequence floors alone decide
        assert found == []

    def test_reordered_body_clears_every_bound_but_not_the_literal_floor(self, lang):
        """Same statements rotated by 3: the multiset bound (0.977 / 0.974) lets the pair through
        to ratio(), which gives shaped 0.250 / 0.385 and literal 0.591 / 0.564 (ruby / lua), under
        the 0.5 shaped and 0.7 literal floors. A literal test against the shaped floor (0.5) would
        report it."""
        base = _function_lines(lang, "base", "base")
        inner = base[1:-1]
        moved = [base[0].replace("base", "var")] + inner[3:] + inner[:3] + [base[-1]]
        content, structure = _build(lang, [("base", base), ("var", moved)])
        rule = D002()
        t1, t2 = (rule._tokens(rule._normalize(extract_function_body(f, content)))
                  for f in structure["functions"])
        literal = SequenceMatcher(None, t1[1], t2[1], autojunk=False)
        assert literal.quick_ratio() >= rule.MIN_LITERAL_MATCH
        assert rule.MIN_SEQUENCE_MATCH <= literal.ratio() < rule.MIN_LITERAL_MATCH
        assert _reported(rule, lang, structure, content) == []

    def test_renamed_pair_just_over_the_shaped_floor_is_reported(self, lang):
        """Every local renamed and one (ruby) or two (lua) lines replaced: shaped 0.511 / 0.533,
        literal 0.600 / 0.507, so only the shaped stage (floor 0.5) reports it. A shaped test
        against the literal floor (0.7) would lose it."""
        renames = {"result": "acc", "items": "rows", "item": "entry", "limit": "cap",
                   "label": "caption", "log_result": "emit_report"}
        pattern = re.compile("|".join(r"\b%s\b" % word for word in renames))
        junk = {"ruby": 1, "lua": 2}[lang]
        var = [pattern.sub(lambda m: renames[m.group(0)], line)
               for line in _function_lines(lang, "var", "var", junk=junk)]
        content, structure = _build(lang, [("base", _function_lines(lang, "base", "base")), ("var", var)])
        rule = D002()
        t1, t2 = (rule._tokens(rule._normalize(extract_function_body(f, content)))
                  for f in structure["functions"])
        ratio = lambda a, b: SequenceMatcher(None, a, b, autojunk=False).ratio()  # noqa: E731
        assert rule.MIN_SEQUENCE_MATCH <= ratio(t1[0], t2[0]) < rule.MIN_LITERAL_MATCH
        assert ratio(t1[1], t2[1]) < rule.MIN_LITERAL_MATCH
        assert len(_reported(rule, lang, structure, content)) == 1
