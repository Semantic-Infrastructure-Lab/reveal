"""BACK-1614: help:// does not hide an adapter whose own help or schema fails.

Each case used to be an ``except Exception`` that returned an empty value: the
adapter listed with no description, left out of the schema menu, or the
anti-patterns topic reported as unknown, with nothing said about why.
"""

import logging
from pathlib import Path

import pytest

from reveal.adapters.base import _ADAPTER_REGISTRY
from reveal.adapters.help import HelpAdapter


class _BrokenAdapter:
    @staticmethod
    def get_help():
        raise ValueError('help data malformed')

    @staticmethod
    def get_schema():
        raise ValueError('schema malformed')


@pytest.fixture
def broken_registered(monkeypatch):
    monkeypatch.setitem(_ADAPTER_REGISTRY, 'brokenx', _BrokenAdapter)


def test_listing_names_the_failure(broken_registered):
    entry = next(a for a in HelpAdapter()._list_adapters() if a['scheme'] == 'brokenx')
    assert entry['description'] == '(help unavailable: ValueError: help data malformed)'


def test_schema_menu_omission_is_logged(broken_registered, caplog):
    with caplog.at_level(logging.WARNING, logger='reveal.adapters.help'):
        schemes = HelpAdapter()._adapters_with_schema()
    assert 'brokenx' not in schemes
    assert 'brokenx:// left out of the schema menu' in caplog.text


def test_see_also_failure_is_logged(broken_registered, caplog):
    data: dict = {}
    with caplog.at_level(logging.WARNING, logger='reveal.adapters.help'):
        HelpAdapter()._add_related_see_also(data, 'brokenx')
    assert 'see_also' not in data
    assert 'help://brokenx: see_also not shown' in caplog.text


def test_unreadable_agent_help_is_an_error_not_an_unknown_topic(monkeypatch):
    real_read = Path.read_text

    def _read(self, *args, **kwargs):
        if self.name == 'AGENT_HELP.md':
            raise PermissionError('denied')
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', _read)
    with pytest.raises(PermissionError):
        HelpAdapter()._get_anti_patterns_section()
