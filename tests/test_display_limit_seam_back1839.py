"""One display-limit seam for overview, deps, architecture and surface (BACK-1839).

``--top`` / ``?top=`` is validated at one point: the CLI argparse type and the URI
router both call ``nonnegative_display_limit``, and the URI router keys on the
renderer's ``ACCEPTS_TOP`` declaration rather than a scheme-name list.
"""

import subprocess
import sys

import pytest

pytestmark = pytest.mark.cli

COMMANDS = ('overview', 'deps', 'architecture', 'surface')
# surface:// has no ?top= parameter (its schema declares none), so its URI form is a
# control: it keeps ignoring the unknown parameter with a warning.
URI_FORMS = ('overview', 'deps', 'architecture')


def _run(*args):
    return subprocess.run([sys.executable, '-m', 'reveal', *map(str, args)],
                          capture_output=True, text=True, encoding='utf-8', timeout=120)


@pytest.fixture(scope='module')
def tree(tmp_path_factory):
    root = tmp_path_factory.mktemp('toplimit')
    (root / 'a.py').write_text(
        'import argparse\nimport b\n\n\ndef small():\n    return b.other()\n\n\n'
        'p = argparse.ArgumentParser()\np.add_argument("--foo")\np.add_argument("--bar")\n',
        encoding='utf-8')
    (root / 'b.py').write_text('def other():\n    return 2\n', encoding='utf-8')
    (root / 'c.js').write_text('function f() { return 1; }\n', encoding='utf-8')
    return root


def _bad_value_message(result, value):
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    err = result.stderr
    assert ('top must be a non-negative integer' in err or
            'top must be a whole number' in err), err
    assert f"'{value}'" in err, err
    assert 'invalid literal' not in err
    assert 'nonnegative_display_limit' not in err
    assert 'Traceback' not in err
    assert 'failed' not in err and 'and 1 more' not in result.stdout


@pytest.mark.parametrize('value', ['-1', 'abc', '1.5'])
@pytest.mark.parametrize('command', COMMANDS)
def test_cli_top_rejects_bad_value_with_one_message(tree, command, value):
    _bad_value_message(_run(command, tree, '--top', value), value)


@pytest.mark.parametrize('value', ['-1', 'abc', '1.5'])
@pytest.mark.parametrize('scheme', URI_FORMS)
def test_uri_top_rejects_bad_value_with_one_message(tree, scheme, value):
    _bad_value_message(_run(f'{scheme}://{tree}?top={value}'), value)


@pytest.mark.parametrize('scheme', ['deps', 'architecture', 'overview'])
def test_uri_integral_float_top_is_accepted(tree, scheme):
    result = _run(f'{scheme}://{tree}?top=1.0')
    assert result.returncode == 0, result.stderr
    assert 'invalid literal' not in result.stderr


@pytest.mark.parametrize('command', ['deps', 'architecture', 'overview', 'surface'])
def test_cli_integral_float_top_is_accepted(tree, command):
    result = _run(command, tree, '--top', '2.0')
    assert result.returncode == 0, result.stderr


# Negative controls: a valid top and a scheme that does not accept top keep working.
@pytest.mark.parametrize('scheme', URI_FORMS)
def test_valid_top_still_renders(tree, scheme):
    assert _run(f'{scheme}://{tree}?top=3').returncode == 0
    assert _run(scheme, tree, '--top', '3').returncode == 0


def test_valid_zero_top_still_renders(tree):
    assert _run('deps', tree, '--top', '0').returncode == 0
    assert _run(f'deps://{tree}?top=0').returncode == 0


def test_scheme_without_top_contract_keeps_ignoring_it(tree):
    stats = _run(f'stats://{tree}?top=-1')
    assert stats.returncode == 0
    assert "query param 'top' has no effect" in stats.stderr
    # Surface now declares top; its earlier pilot rejects invalid values too.
    _bad_value_message(_run(f'surface://{tree}?top=-1'), '-1')
