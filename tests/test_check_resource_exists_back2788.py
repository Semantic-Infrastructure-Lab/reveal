"""``factory.check_resource_exists`` judges a filesystem resource before the adapter is built, as the CLI's declared
route does (``declared._declared_answer``): a path that does not exist is ``PathNotFoundError('Path not found:
PATH')``, an invalid request (BACK-2788)."""
import pytest

from reveal.adapters.factory import check_resource_exists
from reveal.errors import PathNotFoundError, RequestValidationError
from reveal.utils.query_parser import ResourceSpec


class _Files:
    RESOURCE_SPEC = ResourceSpec(filesystem=True)


class _Named:
    """A resource that is no path (env://, help://): nothing to stat."""
    RESOURCE_SPEC = ResourceSpec(filesystem=False)


class _Shorthand(_Files):
    """calls' ``path:name`` names ``path`` (``scope_path_of``)."""
    @staticmethod
    def resource_path(path):
        return path.partition(':')[0]


class _Undeclared:
    pass


def test_a_missing_path_is_path_not_found_as_spelled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(PathNotFoundError) as raised:
        check_resource_exists(_Files, 'nope')
    assert str(raised.value) == 'Path not found: nope'
    assert isinstance(raised.value, RequestValidationError) and isinstance(raised.value, FileNotFoundError)


def test_a_file_under_a_file_is_not_found(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'f.py').write_text('x = 1\n', encoding='utf-8')
    with pytest.raises(PathNotFoundError, match='^Path not found: f.py/g.py$'):
        check_resource_exists(_Files, 'f.py/g.py')


def test_an_existing_path_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'f.py').write_text('x = 1\n', encoding='utf-8')
    check_resource_exists(_Files, 'f.py')
    check_resource_exists(_Files, '.')


def test_the_stat_reads_the_scope(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'f.py').write_text('x = 1\n', encoding='utf-8')
    check_resource_exists(_Shorthand, 'f.py:main')  # scope_path_of: f.py
    check_resource_exists(_Files, 'nope', 'f.py')  # an explicit scope
    with pytest.raises(PathNotFoundError, match='^Path not found: g.py:main$'):
        check_resource_exists(_Shorthand, 'g.py:main')


@pytest.mark.parametrize('adapter', [_Named, _Undeclared])
def test_a_resource_that_is_no_path_is_not_checked(tmp_path, monkeypatch, adapter):
    monkeypatch.chdir(tmp_path)
    check_resource_exists(adapter, 'nope')
