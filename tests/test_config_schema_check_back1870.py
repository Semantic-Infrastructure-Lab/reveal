"""Config validation skips the per-call metaschema check; the schema is checked here instead (BACK-1870)."""

import logging
from pathlib import Path

import pytest

jsonschema = pytest.importorskip('jsonschema')

from reveal.config import CONFIG_SCHEMA, RevealConfig


def test_config_schema_is_itself_valid():
    jsonschema.validators.validator_for(CONFIG_SCHEMA).check_schema(CONFIG_SCHEMA)


def test_invalid_config_still_warns_with_the_schema_message(caplog):
    bad = {'profiles': 'not-a-mapping', 'plugins': 3}
    with caplog.at_level(logging.WARNING, logger='reveal.config'):
        RevealConfig._validate_config_schema(bad, Path('x/.reveal.yaml'))
    msgs = [r.getMessage() for r in caplog.records]
    assert any(m.startswith('Invalid config in x/.reveal.yaml: ') for m in msgs), msgs


def test_valid_config_is_silent(caplog):
    with caplog.at_level(logging.WARNING, logger='reveal.config'):
        RevealConfig._validate_config_schema({}, Path('x/.reveal.yaml'))
    assert not caplog.records
