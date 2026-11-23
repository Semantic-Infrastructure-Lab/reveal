"""No deprecation chains: a RETIREMENTS replacement never names a spelling that itself retires (BACK-2716, D20).

COMMAND_MODEL "Retirement notes" (Scott 2026-11-19): a note teaches the one spelling, so its replacement is the flag
form. It never names an analysis-only scheme (rule 2), a URI query option (``?key=``), or a scheme, subcommand or flag
with a RETIREMENTS row of its own, and every flag it names is one reveal reads. Generated rows are held to it too.
"""
import re

import pytest

from reveal.cli.invocation import COMMANDS, RETIREMENTS, generated_retirements
from reveal.cli.parser import create_argument_parser
from reveal.cli.routing.declared import create_declared_parser, declared_adapter_class
# COMMAND_MODEL rule 2: schemes that name a path and select an analysis. Their requests are `reveal NOUN TARGET`.
from teaching_patterns import ANALYSIS_ONLY, ANALYSIS_URI as _ANALYSIS_URI, QUERY_OPTION as _QUERY_OPTION
_FLAG = re.compile(r'(?<![\w-])--[a-z][\w-]*')
_NOUN = re.compile(r'\breveal ([a-z]+)\b')

ROWS = {**RETIREMENTS, **generated_retirements()}


def _noun_of(key):
    """The noun a param:/flag:/value: row belongs to (``param:calls.top`` -> calls), or None for a global row."""
    match = re.match(r'(?:param|value|flag):([a-z]+)\.', key)
    return match.group(1) if match else None


def _options(noun):
    spec = COMMANDS.get(noun)
    if spec is not None and spec.declared_adapter and declared_adapter_class(spec.declared_adapter) is not None:
        return set(create_declared_parser(spec.declared_adapter)._option_string_actions)
    if spec is not None:
        parser, _ = spec.load()
        return set(parser._option_string_actions)
    return set()


_MAIN = set(create_argument_parser('test')._option_string_actions)


def _readable_flags(key, replacement):
    """The flags a reader of this row can type: the parsers of the nouns it names (``reveal NOUN``) and of its own
    noun, or the main parser and every noun's for a global row."""
    nouns = set(_NOUN.findall(replacement)) | ({_noun_of(key)} - {None})
    if not nouns:
        return _MAIN.union(*(_options(name) for name in COMMANDS))
    return _MAIN.union(*(_options(noun) for noun in nouns))


@pytest.mark.parametrize('key', sorted(ROWS))
def test_a_replacement_names_no_analysis_only_scheme_and_no_query_option(key):
    replacement = ROWS[key].replacement
    assert not _ANALYSIS_URI.search(replacement), f'{key}: names an analysis-only scheme: {replacement}'
    assert not _QUERY_OPTION.search(replacement), f'{key}: names a URI query option: {replacement}'


@pytest.mark.parametrize('key', sorted(ROWS))
def test_a_replacement_names_no_spelling_with_a_retirement_row_of_its_own(key):
    replacement = ROWS[key].replacement
    noun = _noun_of(key)
    for flag in _FLAG.findall(replacement):
        assert f'flag:{flag}' not in RETIREMENTS, f'{key}: names the retired flag {flag}'
        for owner in {noun, *_NOUN.findall(replacement)} - {None}:
            assert f'flag:{owner}.{flag}' not in RETIREMENTS, f'{key}: names the retired {owner} flag {flag}'
    for word in _NOUN.findall(replacement):
        assert f'subcommand:{word}' not in RETIREMENTS, f'{key}: names the retired subcommand reveal {word}'
    for scheme in re.findall(r'\b([a-z]+)://', replacement):
        assert f'scheme:{scheme}' not in RETIREMENTS, f'{key}: names the retired scheme {scheme}://'


@pytest.mark.parametrize('key', sorted(ROWS))
def test_every_flag_a_replacement_names_is_one_reveal_reads(key):
    replacement = ROWS[key].replacement
    readable = _readable_flags(key, replacement)
    unknown = [flag for flag in _FLAG.findall(replacement) if flag not in readable]
    assert not unknown, f'{key}: names flags no parser in its context reads: {unknown} in {replacement}'


def test_the_declared_analysis_only_schemes_are_the_ten_of_rule_2():
    assert set(ANALYSIS_ONLY) == {'ast', 'calls', 'imports', 'markdown', 'metrics', 'overview', 'patches', 'surface',
                                  'contracts', 'pack'}


def test_the_red_control_a_chained_replacement_fails():
    """The checks see the old forms they replaced (semantic red control)."""
    assert _ANALYSIS_URI.search('calls://<path>?callees=FUNC&depth=N&detail')
    assert _QUERY_OPTION.search('?limit=N (--limit N); 0 is uncapped')
    assert _QUERY_OPTION.search('--offset START-1 (?offset=START-1&limit=END-START+1)')
    assert not _QUERY_OPTION.search('claude://session/NAME --match TEXT')
