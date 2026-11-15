"""BACK-2649: the empty-?callers widening hint must not leak the parent scan's per-file warnings.

R (``tmp_path / 'root'``) holds ``caller.py``, a caller of ``target``, and ``outside.ipynb``, a
malformed notebook. P (``R / 'pkg'``) defines ``target`` and calls nothing, so ``?callers=target`` on
P is empty and the hint scans R. The in-scope ``Failed to analyze`` warning is pinned behaviour;
the advisory scan of R must not print one for a file the user never asked about (on the CLI it
is noise; over MCP it is appended after the JSON as ``[stderr: ...]``).
"""
import json
import re
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.utils.path_utils import is_unsafe_scan_root

OUTSIDE = 'outside.ipynb'
INSIDE = 'inside.ipynb'
MALFORMED = '{"cells": [\n'  # the notebook that turned CI red (tests/test_back_1083_check_contract_disclosure.py)


@pytest.fixture
def root(tmp_path, monkeypatch):
    # R lives under tmp_path, so the hint's parent scan never reaches pytest's shared basetemp.
    root = tmp_path / 'root'
    pkg = root / 'pkg'
    pkg.mkdir(parents=True)
    (pkg / 'lib.py').write_text('def target():\n    return 1\n', encoding='utf-8')
    (root / 'caller.py').write_text('from pkg.lib import target\n\n\ndef use():\n    return target()\n',
                                    encoding='utf-8')
    (root / OUTSIDE).write_text(MALFORMED, encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('REVEAL_MAX_WORKERS', '1')
    # The hint refuses to scan a system/home/temp root; R must not be one or nothing below fires.
    assert not is_unsafe_scan_root(root)
    return root


def warning_lines(stderr, name):
    return [line for line in stderr.split('\n') if 'Failed to analyze' in line and name in line]


def potential_count(hint):
    match = re.search(r'(\d+) potential caller\(s\)', hint or '')
    return int(match.group(1)) if match else None


def mcp_text(path):
    from reveal.mcp_server import _ToolFailure, reveal_query
    # provenance=True is the tool's JSON form: it forces --format json (the tool has no format argument).
    text = reveal_query(f'calls://{path.as_posix()}?callers=target', provenance=True)
    assert not isinstance(text, _ToolFailure), f'MCP unexpectedly failed: {text}'
    return text


class TestPreservation:
    def test_hint_still_counts_the_out_of_scope_caller(self, root):
        result = run('calls', root / 'pkg', '--callers', 'target', '--format', 'json')
        assert result.returncode == 0, result.stderr
        answer = json.loads(result.stdout)
        assert answer['total_callers'] == 0
        assert potential_count(answer.get('hint')) == 1, answer.get('hint')
        text = run('calls', root / 'pkg', '--callers', 'target')
        assert 'Hint:' in text.stdout and potential_count(text.stdout) == 1, text.stdout

    def test_in_scope_unparseable_file_still_warns_on_the_cli(self, root):
        (root / 'pkg' / INSIDE).write_text(MALFORMED, encoding='utf-8')
        result = run('calls', root / 'pkg', '--callers', 'target')
        assert warning_lines(result.stderr, INSIDE), f'in-scope warning lost: {result.stderr!r}'

    def test_sibling_collect_structures_consumer_still_warns(self, root):
        result = run(f'ast://{root.as_posix()}')
        assert warning_lines(result.stderr, OUTSIDE), f'ast:// warning lost: {result.stderr!r}'

    def test_non_empty_answer_prints_no_hint_and_never_scans_the_parent(self, root):
        (root / 'pkg' / 'internal.py').write_text(
            'from pkg.lib import target\n\n\ndef inner():\n    return target()\n', encoding='utf-8')
        result = run('calls', root / 'pkg', '--callers', 'target', '--format', 'json')
        assert result.returncode == 0, result.stderr
        answer = json.loads(result.stdout)
        callers = [(Path(c['file']).name, c['caller']) for level in answer['levels'] for c in level['callers']]
        assert (answer['total_callers'], callers) == (1, [('internal.py', 'inner')])
        assert 'hint' not in answer
        assert warning_lines(result.stderr, OUTSIDE) == [], result.stderr

    def test_mcp_json_parses_when_the_parent_holds_no_unparseable_file(self, root):
        # Control for the MCP red below: the same query is one JSON document once R parses cleanly.
        (root / OUTSIDE).unlink()
        answer = json.loads(mcp_text(root / 'pkg'))
        assert potential_count(answer.get('hint')) == 1, answer.get('hint')


class TestOutOfScopeWarningLeak:
    @pytest.mark.parametrize('fmt', ['text', 'json'])
    def test_cli_prints_no_warning_for_a_file_outside_the_requested_scope(self, root, fmt):
        result = run('calls', root / 'pkg', '--callers', 'target', '--format', fmt)
        assert result.returncode == 0, result.stderr
        assert potential_count(result.stdout) == 1, 'the hint must still fire, or this proves nothing'
        leaked = warning_lines(result.stderr, OUTSIDE)
        assert leaked == [], f'the parent-hint scan warned about a file outside {root / "pkg"}: {leaked}'

    def test_mcp_reveal_query_json_is_one_document(self, root):
        text = mcp_text(root / 'pkg')
        try:
            answer = json.loads(text)
        except json.JSONDecodeError as error:
            pytest.fail(f'reveal_query text is not one JSON document ({error}); after the JSON: {text[error.pos:]!r}')
        assert potential_count(answer.get('hint')) == 1, answer.get('hint')

    def test_in_scope_unparseable_file_warns_exactly_once(self, root):
        # The hint's scan of R walks P again; it must not repeat the in-scope warning the answer already printed.
        (root / 'pkg' / INSIDE).write_text(MALFORMED, encoding='utf-8')
        result = run('calls', root / 'pkg', '--callers', 'target')
        assert potential_count(result.stdout) == 1, 'the hint must still fire, or this proves nothing'
        lines = warning_lines(result.stderr, INSIDE)
        assert len(lines) == 1, f'expected the in-scope warning once, got {len(lines)}: {lines}'


class TestQuietCollection:
    """collect_structures(warn=False) drops only the stderr line; the loss stays in ``skipped``."""

    @pytest.mark.parametrize('target', ['dir', 'file'])
    def test_warn_false_records_the_skip_without_printing(self, root, capsys, target):
        from reveal.adapters.ast.analysis import collect_structures
        path = root if target == 'dir' else root / OUTSIDE
        loud = collect_structures(str(path))
        loud_err = capsys.readouterr().err
        quiet = collect_structures(str(path), warn=False)
        quiet_err = capsys.readouterr().err
        assert warning_lines(loud_err, OUTSIDE), f'default must still warn: {loud_err!r}'
        assert warning_lines(quiet_err, OUTSIDE) == [], quiet_err
        assert [Path(f).name for f, _ in quiet.skipped] == [Path(f).name for f, _ in loud.skipped] == [OUTSIDE]
        assert len(quiet) == len(loud)


class TestHintCache:
    """Inside one host request the hint reuses a cached parent index instead of parsing the parent again."""

    @pytest.fixture
    def collections(self, monkeypatch):
        from reveal.adapters.calls import index as calls_index
        seen = []
        real = calls_index.collect_structures

        def counting(path, *args, **kwargs):
            seen.append((Path(path).name, kwargs.get('warn', True)))
            return real(path, *args, **kwargs)

        monkeypatch.setattr(calls_index, 'collect_structures', counting)
        calls_index._INDEX_CACHE.clear()
        yield seen
        calls_index._INDEX_CACHE.clear()

    def test_hint_after_a_parent_query_collects_only_the_requested_scope(self, root, collections):
        from reveal.adapters.calls.index import find_callers
        from reveal.utils.request_cache import host_request
        with host_request():
            assert find_callers(str(root), 'target')['total_callers'] == 1
            collections.clear()
            answer = find_callers(str(root / 'pkg'), 'target')
        assert potential_count(answer.get('hint')) == 1, answer.get('hint')
        assert collections == [('pkg', True)], f'the hint parsed the cached parent again: {collections}'

    def test_hint_on_a_miss_collects_the_parent_once_quietly(self, root, collections):
        from reveal.adapters.calls.index import find_callers
        from reveal.utils.request_cache import host_request
        with host_request():
            answer = find_callers(str(root / 'pkg'), 'target')
        assert potential_count(answer.get('hint')) == 1, answer.get('hint')
        assert collections == [('pkg', True), ('root', False)], collections


class TestHintWording:
    """The count is a lower bound when the quiet parent scan skipped a file it could not analyze."""

    def hint(self, root):
        result = run('calls', root / 'pkg', '--callers', 'target', '--format', 'json')
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout).get('hint', '')

    def test_skipped_parent_file_makes_the_count_a_lower_bound(self, root):
        hint = self.hint(root)
        assert 'at least 1 potential caller(s)' in hint, hint

    def test_clean_parent_keeps_the_plain_count(self, root):
        (root / OUTSIDE).unlink()
        hint = self.hint(root)
        assert '1 potential caller(s)' in hint and 'at least' not in hint, hint
