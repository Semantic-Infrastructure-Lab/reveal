"""env:// redaction covers plural names and URL credentials (BACK-2213)."""
import pytest

from reveal.adapters.env import EnvAdapter


@pytest.fixture
def adapter(monkeypatch):
    for k in list(__import__('os').environ):
        monkeypatch.delenv(k)
    monkeypatch.setenv('DATABASE_URL', 'postgres://user:hunter2@db:5432/app')
    monkeypatch.setenv('AWS_CREDENTIALS', 'abc123')
    monkeypatch.setenv('DB_CREDENTIALS', 'abc123')
    monkeypatch.setenv('CACHE_ENDPOINT', 'redis://u:pw@cache:6379/0')
    monkeypatch.setenv('PLAIN_URL', 'https://example.com/path')
    return EnvAdapter()


@pytest.mark.parametrize('name', ['DATABASE_URL', 'AWS_CREDENTIALS', 'DB_CREDENTIALS', 'CACHE_ENDPOINT'])
def test_secret_values_redacted(adapter, name):
    result = adapter.get_element(name)
    assert result['value'] == '***'
    assert result['sensitive'] is True


def test_plain_url_not_redacted(adapter):
    result = adapter.get_element('PLAIN_URL')
    assert result['value'] == 'https://example.com/path'
    assert result['sensitive'] is False


@pytest.fixture
def env(monkeypatch):
    def make(**values):
        for key in list(__import__('os').environ):
            monkeypatch.delenv(key)
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        return EnvAdapter()
    return make


@pytest.mark.parametrize('name,value', [
    ('PGPASSWORD', 'hunter2'),
    ('MYSQL_PWD', 'hunter2'),
    ('PASSWD', 'hunter2'),
    ('DB_PWD', 'hunter2'),
    ('SQLSERVER_CONNECTION_STRING', 'Server=x;User Id=u;Password=p;'),
    ('PLAIN_NAME_A', 'Server=x;User Id=u;Password=p;'),
    ('PLAIN_NAME_B', 'Server=x;Pwd=p'),
    ('PLAIN_NAME_C', 'postgres://u@h/db?password=x'),
    ('PLAIN_NAME_D', 'https://h/p?a=1&passwd=x'),
    ('PLAIN_NAME_E', '"postgres://u:pw@h/db"'),
    ('PLAIN_NAME_F', ' postgres://u:pw@h'),
    ('PLAIN_NAME_G', 'jdbc:mysql://u:p@h/db'),
])
def test_more_secret_shapes_are_redacted(env, name, value):
    result = env(**{name: value}).get_element(name)
    assert result['value'] == '***' and result['sensitive'] is True


@pytest.mark.parametrize('name,value', [
    ('PWD', '/home/user'),
    ('KEYBOARD', 'us'),
    ('MONKEY', 'see'),
    ('AUTHOR', 'me'),
    ('SOME_URL', 'https://example.com/path?page=2&sort=asc'),
    ('NOTE', 'password rotation is monthly'),
])
def test_ordinary_variables_are_not_redacted(env, name, value):
    result = env(**{name: value}).get_element(name)
    assert result['value'] == value and result['sensitive'] is False


def test_structure_and_metadata_agree_with_the_element_path(env):
    adapter = env(PGPASSWORD='x', PLAIN='postgres://u:p@h/db', HARMLESS='1')
    rows = {r['name']: r for cat in adapter.get_structure()['categories'].values() for r in cat}
    assert rows['PGPASSWORD']['value'] == '***' and rows['PLAIN']['value'] == '***'
    assert rows['HARMLESS']['value'] == '1'
    assert adapter.get_metadata()['sensitive_variables'] == 2
