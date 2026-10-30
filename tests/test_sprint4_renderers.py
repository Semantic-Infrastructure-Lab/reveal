"""Sprint 4 real-command controls for renderer usage errors and diagnostics."""

import re
import subprocess
import sys

import pytest


def _run(*args):
    return subprocess.run([sys.executable, '-m', 'reveal', *map(str, args)],
                          capture_output=True, text=True, encoding='utf-8', timeout=60)


@pytest.mark.parametrize('command,uri', [
    ('deps', 'deps'), ('architecture', 'architecture'),
])
def test_negative_top_is_usage_error_in_both_forms(tmp_path, command, uri):
    (tmp_path / 'a.py').write_text('import b\ndef small():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('def other():\n    return 2\n', encoding='utf-8')
    for args in ((command, tmp_path, '--top', '-1'),
                 (f'{uri}://{tmp_path}?top=-1',)):
        result = _run(*args)
        assert result.returncode == 2
        assert 'top' in result.stderr.lower()
        assert 'Traceback' not in result.stderr


def test_real_clean_hotspots_result_keeps_clean_verdict(tmp_path):
    (tmp_path / 'clean.py').write_text('def small():\n    return 1\n', encoding='utf-8')
    result = _run('hotspots', tmp_path)
    assert result.returncode == 0
    assert 'No hotspots found in the requested analyzed population.' in result.stdout
    assert 'Code quality looks good' not in result.stdout  # BACK-1974: no all-clear claim
    assert 'complexity is McCabe' in result.stdout


def test_empty_hotspots_does_not_call_internal_filter_a_typo(tmp_path):
    result = _run('hotspots', tmp_path)
    assert result.returncode == 0
    assert 'Filter key(s)' not in result.stdout
    assert 'Code quality looks good' not in result.stdout


def test_parse_degraded_hotspots_never_claims_clean(tmp_path):
    (tmp_path / 'broken.py').write_text('def broken(:\n    pass\n', encoding='utf-8')
    result = _run('hotspots', tmp_path)
    assert result.returncode == 3  # required parse loss is incomplete analysis (D6), not a clean 0
    assert 'Code quality looks good' not in result.stdout


def _diagnostic_lines(result):
    """Diagnostics from both streams, prefix-normalised: `⚠ text` lines and `Warning: text` lines."""
    lines = result.stdout.splitlines() + result.stderr.splitlines()
    return [re.sub(r'^(?:\s*⚠\s*)+|^Warning:\s*', '', line)
            for line in lines if '⚠' in line or line.startswith('Warning:')]


@pytest.mark.parametrize('command', [
    'deps', 'contracts', 'pack', 'architecture', 'hotspots', 'surface',
])
def test_migrated_subcommands_emit_each_diagnostic_once(tmp_path, command):
    # Six .sh files have no import extraction, so every subcommand has something to warn about
    # (pack warns on stderr, the others on stdout). Plain .lua files gave pack and architecture none.
    (tmp_path / 'app.py').write_text('def small():\n    return 1\n', encoding='utf-8')
    for index in range(6):
        (tmp_path / f'foreign_{index}.sh').write_text('echo hi\n', encoding='utf-8')
    if command == 'architecture':
        # The compact map does not request assessment of unsupported shell files.
        # Required import parse loss supplies an actual map diagnostic.
        (tmp_path / 'broken.py').write_text('def broken(:\n', encoding='utf-8')
    result = _run(command, tmp_path)
    assert result.returncode in (0, 1, 3)
    warnings = _diagnostic_lines(result)
    assert warnings, f'{command}: fixture produced no diagnostic, so "once" proves nothing'
    assert len(warnings) == len(set(warnings)), warnings
    if command == 'surface':
        assert result.stdout.count('source files') == 1
        uri_result = _run(f'surface://{tmp_path}')
        assert uri_result.stdout.count('source files') == 1


def test_renderer_compat_exports_do_not_silently_change_print_semantics():
    from reveal.adapters import deps
    from reveal.adapters import contracts
    assert not hasattr(deps, '_render_deps')
    assert not hasattr(contracts, '_render_report')
