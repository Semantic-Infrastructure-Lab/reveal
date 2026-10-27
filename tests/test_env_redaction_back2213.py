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
