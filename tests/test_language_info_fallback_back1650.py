"""BACK-1650: `--language-info` answers for the tree-sitter fallback languages.

`--languages` lists haskell/elm/erlang/ocaml/r/verilog/objc as fallback languages and
`reveal a.hs` opens them, but `--language-info haskell` said "Language not found" and
`--language-info .hs` said "Extension not supported". `--language-info` is text-only
(it declares that --format has no effect), so the JSON side of the contract is
`--languages --format json`: every fallback it lists must resolve here.
"""

import json
import subprocess
import sys

import pytest

from reveal.capabilities import CONFORMANCE_UNTESTED
from reveal.cli.introspection import get_language_info_detailed, resolve_language
from reveal.registry import FALLBACK_SUPPORT_NOTE, fallback_languages

FALLBACK_NAMES = ['haskell', 'elm', 'erlang', 'ocaml', 'r', 'verilog', 'objc', 'objective-c']


@pytest.mark.parametrize('name', FALLBACK_NAMES)
def test_fallback_language_name_resolves(name):
    ext, info, error = resolve_language(name)
    assert error is None, error
    assert info['is_fallback'] is True
    assert ext in fallback_languages()


@pytest.mark.parametrize('name', FALLBACK_NAMES)
def test_fallback_text_uses_shared_note_and_untested_level(name):
    text = get_language_info_detailed(name)
    assert FALLBACK_SUPPORT_NOTE in text
    assert f'Conformance level: {CONFORMANCE_UNTESTED}' in text


@pytest.mark.parametrize('ext', ['.hs', '.m', '.mm', '.ml', '.sv'])
def test_fallback_extension_resolves(ext):
    _, info, error = resolve_language(ext)
    assert error is None, error
    assert info['is_fallback'] is True


def test_r_is_the_r_language_not_a_substring_match():
    ext, info, error = resolve_language('r')
    assert error is None, error
    assert (ext, info['fallback_language']) == ('.r', 'r')


def test_every_fallback_in_languages_json_resolves():
    proc = subprocess.run(
        [sys.executable, '-m', 'reveal', '--languages', '--format', 'json'],
        capture_output=True, text=True, timeout=120, encoding='utf-8',
    )
    assert proc.returncode == 0, proc.stderr
    listed = json.loads(proc.stdout)['fallback']
    assert listed
    for entry in listed:
        for ext in entry['extensions']:
            _, info, error = resolve_language(ext)
            assert error is None, (entry['name'], ext, error)
        assert resolve_language(entry['name'])[2] is None, entry['name']


@pytest.mark.parametrize('name', ['python', 'rust', 'c++'])
def test_explicit_languages_unchanged(name):
    ext, info, error = resolve_language(name)
    assert error is None, error
    assert info['is_fallback'] is False
    assert 'Tree-sitter Fallback' not in get_language_info_detailed(name)


def test_unknown_language_still_not_found():
    _, info, error = resolve_language('nonexistent_lang_12345')
    assert info is None and 'Language not found' in error
