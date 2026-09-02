"""BACK-906: every cli/commands/*.py --format json payload carries the
Output Contract envelope (contract_version/type/source/source_type),
matching what V023 already enforces for adapters/analyzers.

Static, source-pattern style (mirrors V023's own approach rather than
executing each command) — cheap and catches the exact regression V023
found: a bare `json.dumps(report, ...)` that skips
`add_cli_contract_fields()` and ships an un-enveloped payload.
"""

import re
import unittest
from pathlib import Path

import pytest

# BACK-1149: component-layer test -- calls a reveal.cli.* handler function directly, not through reveal.main
pytestmark = pytest.mark.component

_COMMANDS_DIR = Path(__file__).parent.parent / 'reveal' / 'cli' / 'commands'

# file -> number of --format json print sites that must be enveloped.
_EXPECTED_JSON_SITES = {
    'architecture.py': 2,
    'overview.py': 1,
    'pack.py': 1,
    'surface.py': 1,
    'review.py': 1,
    'contracts.py': 1,
    'health.py': 1,
    'testability.py': 1,
    'hotspots.py': 1,
    'deps.py': 1,
    'trace.py': 1,
}


class TestCliJsonContract(unittest.TestCase):
    """Every raw json.dumps() call in cli/commands/ must be wrapped by
    add_cli_contract_fields() so --format json output always carries the
    Output Contract envelope."""

    def test_every_known_json_dumps_site_is_enveloped(self):
        for filename, expected_sites in _EXPECTED_JSON_SITES.items():
            with self.subTest(file=filename):
                content = (_COMMANDS_DIR / filename).read_text(encoding='utf-8')
                dumps_calls = re.findall(r'json\.dumps\(', content)
                self.assertEqual(
                    len(dumps_calls), expected_sites,
                    f"{filename}: expected {expected_sites} json.dumps() call(s), "
                    f"found {len(dumps_calls)} — update _EXPECTED_JSON_SITES if this "
                    f"is an intentional new/removed JSON output site."
                )
                envelope_calls = len(re.findall(r'add_cli_contract_fields\(', content))
                self.assertGreaterEqual(
                    envelope_calls, expected_sites,
                    f"{filename} has a json.dumps() call not wrapped by "
                    f"add_cli_contract_fields() — every --format json payload must "
                    f"carry contract_version/type/source/source_type (BACK-906)."
                )

    def test_no_other_cli_command_has_unenveloped_json_dumps(self):
        """Any *other* file in cli/commands/ that starts using json.dumps() for
        its --format json output must also envelope it — this catches new
        commands added after BACK-906, not just the 11 known at fix time."""
        for path in sorted(_COMMANDS_DIR.glob('*.py')):
            if path.name in _EXPECTED_JSON_SITES or path.name == '__init__.py':
                continue
            with self.subTest(file=path.name):
                content = path.read_text(encoding='utf-8')
                dumps_calls = len(re.findall(r'json\.dumps\(', content))
                envelope_calls = len(re.findall(r'add_cli_contract_fields\(', content))
                self.assertGreaterEqual(
                    envelope_calls, dumps_calls,
                    f"{path.name} has {dumps_calls} json.dumps() call(s) but only "
                    f"{envelope_calls} add_cli_contract_fields() call(s) — new "
                    f"--format json output must carry the Output Contract envelope."
                )


class TestBack1178MetaContractVersionParity(unittest.TestCase):
    """BACK-1178: cli/commands/*.py's --format json envelope must keep the
    adapter's own 'contract_version'/'meta' rather than stripping them and
    re-deriving a 1.0/no-meta envelope from add_cli_contract_fields() -- that
    split made the subcommand form disagree with its uri:// twin over the
    same payload. Round 1 fixed 6 files (overview/hotspots/deps/surface/
    contracts/architecture) but missed trace.py, which had the byte-identical
    strip pattern and went undetected because TestCliJsonContract above only
    checks envelope *presence*, not which keys survive it. Static, so it
    catches a reintroduced 'contract_version'/'meta' entry in the strip
    tuple without needing to execute each command."""

    _FILES = (
        'overview.py', 'hotspots.py', 'deps.py', 'surface.py',
        'contracts.py', 'architecture.py', 'trace.py',
    )

    def test_strip_tuple_keeps_contract_version_and_meta(self):
        for filename in self._FILES:
            with self.subTest(file=filename):
                content = (_COMMANDS_DIR / filename).read_text(encoding='utf-8')
                strip_tuples = re.findall(r"if k not in \(([^)]*)\)", content)
                self.assertTrue(
                    strip_tuples,
                    f"{filename}: expected a 'if k not in (...)' report-rebuild "
                    f"strip tuple; update this test if the pattern changed.",
                )
                for tup in strip_tuples:
                    self.assertNotIn(
                        "'contract_version'", tup,
                        f"{filename} strips 'contract_version' from its own "
                        f"report before enveloping -- reintroduces BACK-1178's "
                        f"1.0-vs-1.1 split against the uri:// form.",
                    )
                    self.assertNotIn(
                        "'meta'", tup,
                        f"{filename} strips 'meta' from its own report before "
                        f"enveloping -- reintroduces BACK-1178's split against "
                        f"the uri:// form.",
                    )


class TestCheckJsonContract(unittest.TestCase):
    """BACK-962: check.py's own --format json output lives in reveal/checks.py
    and reveal/cli/file_checker.py, not cli/commands/check.py (which has zero
    json.dumps calls and delegates entirely) — so BACK-906's cli/commands/-only
    sweep and its regression test above never saw these sites. Covered here
    explicitly rather than widening _COMMANDS_DIR, since these two files are
    check-specific helpers, not general cli/commands/ output."""

    _REVEAL_DIR = Path(__file__).parent.parent / 'reveal'

    # file (relative to reveal/) -> number of JSON serialization sites.
    # BACK-1248 added a second site to each file: --also-json writes check's
    # report to a path while a text/grep report goes to stdout. Both sites in
    # a file serialize the SAME enveloping builder (_build_detections_json /
    # _build_json_report), so the envelope assertion below counts builders,
    # not a 1:1 site-to-envelope ratio.
    _EXPECTED_CHECK_JSON_SITES = {
        'checks.py': 2,
        'cli/file_checker.py': 3,
    }

    # file -> the enveloping builder its --also-json site shares with stdout.
    _EXPECTED_ENVELOPE_BUILDERS = {
        'checks.py': '_build_detections_json',
        'cli/file_checker.py': '_build_json_report',
    }

    def test_check_json_dumps_sites_are_enveloped(self):
        for relpath, expected_sites in self._EXPECTED_CHECK_JSON_SITES.items():
            with self.subTest(file=relpath):
                content = (self._REVEAL_DIR / relpath).read_text(encoding='utf-8')
                dumps_calls = len(re.findall(r'json\.dumps\(', content))
                dumps_json_calls = len(re.findall(r'safe_json_dumps\(', content))
                total_calls = dumps_calls + dumps_json_calls
                self.assertEqual(
                    total_calls, expected_sites,
                    f"{relpath}: expected {expected_sites} json.dumps()/"
                    f"safe_json_dumps() call(s), found {total_calls} — update "
                    f"_EXPECTED_CHECK_JSON_SITES if this is intentional."
                )
                # Each serialization site must emit an enveloped document —
                # either by calling add_cli_contract_fields() itself, or by
                # rendering the shared builder that does. Counting both is what
                # lets --also-json reuse a builder (BACK-1248) without either
                # loosening the guard or forcing a duplicate envelope call.
                envelope_calls = len(re.findall(r'add_cli_contract_fields\(', content))
                builder = self._EXPECTED_ENVELOPE_BUILDERS[relpath]
                builder_calls = len(re.findall(rf'(?<!def ){builder}\(', content))
                self.assertGreaterEqual(
                    envelope_calls + builder_calls, total_calls,
                    f"{relpath}: {total_calls} serialization site(s) but only "
                    f"{envelope_calls} add_cli_contract_fields() + {builder_calls} "
                    f"{builder}() call(s) — a `reveal check` JSON output path is "
                    f"emitting a document without the Output Contract envelope "
                    f"(BACK-962/BACK-1248)."
                )


class TestAddCliContractFields(unittest.TestCase):
    """Unit tests for the envelope helper itself."""

    def test_adds_required_fields_without_removing_existing_keys(self):
        from reveal.utils.results import add_cli_contract_fields

        report = {'path': '/tmp/x', 'risks': ['a']}
        enveloped = add_cli_contract_fields(
            report, result_type='architecture', source='/tmp/x',
        )
        self.assertEqual(enveloped['contract_version'], '1.0')
        self.assertEqual(enveloped['type'], 'architecture')
        self.assertEqual(enveloped['source'], '/tmp/x')
        self.assertEqual(enveloped['source_type'], 'directory')
        # Original keys survive untouched.
        self.assertEqual(enveloped['path'], '/tmp/x')
        self.assertEqual(enveloped['risks'], ['a'])
        # Original dict is not mutated.
        self.assertNotIn('contract_version', report)

    def test_source_is_stringified(self):
        from pathlib import Path as PathlibPath
        from reveal.utils.results import add_cli_contract_fields

        p = PathlibPath('tmp') / 'y'
        enveloped = add_cli_contract_fields(
            {}, result_type='deps', source=p,
        )
        self.assertEqual(enveloped['source'], str(p))
        self.assertIsInstance(enveloped['source'], str)

    def test_source_type_and_contract_version_are_overridable(self):
        from reveal.utils.results import add_cli_contract_fields

        enveloped = add_cli_contract_fields(
            {}, result_type='health', source='a,b', source_type='multi',
            contract_version='1.1',
        )
        self.assertEqual(enveloped['source_type'], 'multi')
        self.assertEqual(enveloped['contract_version'], '1.1')


if __name__ == '__main__':
    unittest.main()
