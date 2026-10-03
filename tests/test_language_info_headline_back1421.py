"""BACK-1421: `--language-info` headed every explicit analyzer "✅ Full Language Support",
directly above its own "Conformance level: smoke-tested" (Dart, Scala) or "untested"
(GraphQL, CSV) line. The headline now states the conformance level.
"""

import pytest

from reveal.cli.introspection import _SUPPORT_HEADLINES, get_language_info_detailed


def test_every_conformance_level_has_its_own_headline():
    from reveal.capabilities import _CONFORMANCE_LEVELS
    assert set(_SUPPORT_HEADLINES) == set(_CONFORMANCE_LEVELS)


@pytest.mark.parametrize('name', ['python', 'dart', 'graphql'])
def test_headline_names_the_conformance_level(name):
    text = get_language_info_detailed(name)
    assert 'Full Language Support' not in text
    level = text.split('Conformance level: ', 1)[1].split()[0]
    assert _SUPPORT_HEADLINES[level] in text
