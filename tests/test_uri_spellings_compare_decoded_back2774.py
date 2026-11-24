"""Two spellings of one control in a query string compare as the URI codec decodes them (BACK-2774).

COMMAND_MODEL "Conflicting values": two spellings that give one value are one setting; two values exit 2 naming both.
The URI binder compared a control's spellings (its name, an alias, a legacy word) before decoding them, so a control
whose URI codec is not ``raw`` met its own raw text there: a comma-percent list (patches' test roots once it has a
legacy word) was refused as "must be a valid array" whatever the values, and a percent-encoded spelling of a value
(Calls ``?callers=main&target=m%61in``) conflicted with the same value typed plainly. The values are still kept as
given and decoded once, when the request binds; only the comparison reads them decoded.
"""
import pytest

from conftest import _run_reveal_direct as run
from reveal.utils.query_binding import bind_declared_params
from reveal.utils.query_parser import LegacySpelling, ParamSpec


def _roots(value):
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError('roots must contain at least one path')
    return tuple(value)


ROOTS = ParamSpec('roots', 'array', 'paths', None, _roots, uri_codec='comma-percent', aliases=('root_paths',),
                  legacy=(LegacySpelling('dirs'),))


@pytest.mark.parametrize('query', ['roots=a,b&dirs=a,b', 'roots=a,b&root_paths=a,b', 'roots=a%2Fx&dirs=a/x'])
def test_equal_spellings_of_a_comma_percent_list_are_one_value(query):
    params = bind_declared_params([ROOTS], query, transport='uri')
    expected = bind_declared_params([ROOTS], query.partition('&')[0], transport='uri')
    assert ROOTS.read(params) == ROOTS.read(expected)


@pytest.mark.parametrize('query', ['roots=a&dirs=b', 'roots=a,b&dirs=a'])
def test_different_spellings_of_a_comma_percent_list_name_both(query):
    with pytest.raises(ValueError) as raised:
        bind_declared_params([ROOTS], query, transport='uri')
    assert 'roots' in str(raised.value) and 'dirs' in str(raised.value), str(raised.value)


def test_one_spelling_and_the_typed_transport_are_unchanged():
    """Negative controls: a single spelling decodes as before; a typed list is compared as given."""
    assert ROOTS.read(bind_declared_params([ROOTS], 'roots=a%2Cb,c', transport='uri')) == ('a,b', 'c')
    typed = bind_declared_params([ROOTS], {'roots': ['a'], 'dirs': ['a']}, transport='typed')
    assert ROOTS.read(typed) == ('a',)
    with pytest.raises(ValueError):
        bind_declared_params([ROOTS], {'roots': ['a'], 'dirs': ['b']}, transport='typed')


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / 'app.py').write_text('def main():\n    helper()\n\n\ndef helper():\n    return 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_a_percent_encoded_spelling_of_the_same_value_is_one_setting(project):
    """Through an existing entry point: Calls' callers and its legacy word target (a percent-codec control)."""
    plain = run('calls://.?callers=helper', '--format', 'json')
    encoded = run('calls://.?callers=helper&target=h%65lper', '--format', 'json')
    assert plain.returncode == 0, plain.stderr
    assert encoded.returncode == 0, encoded.stderr
    different = run('calls://.?callers=helper&target=main', '--format', 'json')
    assert different.returncode == 2 and 'callers' in different.stderr and 'target' in different.stderr, \
        different.stderr
