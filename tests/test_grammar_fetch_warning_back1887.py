"""A file with no tree-sitter grammar gets no network-fetch warning (BACK-1887).

``calls://<dir>?uncalled`` lists Windows batch labels (``reveal/analyzers/batch.py``, no
grammar) as functions of family ``''``. The reference scan then asked the parser seam
for language ``''`` and ``get_parser`` warned "tree-sitter grammar for '' not yet
downloaded -- first parse will attempt to fetch it from the network", on every run,
warm cache or cold. No fetch happens for an empty language: the pack refuses it. The
control: a real grammar that is not in the cache must still be announced (BACK-979).
"""

import textwrap
from unittest.mock import patch

import pytest

import reveal.core.treesitter_parse as seam
from reveal.adapters.calls.references import non_python_referenced_names

pytestmark = pytest.mark.component

# The labels of python-celery's docs/make.bat that trigger it: `help` occurs again in
# the file (`goto help`), so the reference scan parses it.
MAKE_BAT = textwrap.dedent("""\
    @ECHO OFF
    if "%1" == "" goto help
    if "%1" == "help" (
    \t:help
    \techo.Please use `make ^<target^>` where ^<target^> is one of
    \tgoto end
    )
    :end
    """)


@pytest.fixture(autouse=True)
def _fresh_seam_state():
    seam._warned_uncached.clear()
    seam._ready.clear()
    yield
    seam._warned_uncached.clear()
    seam._ready.clear()


def _fetch_warnings(caplog):
    return [r.getMessage() for r in caplog.records if 'not yet downloaded' in r.getMessage()]


class TestEmptyLanguage:
    def test_empty_language_is_unavailable_without_a_fetch_claim(self, caplog):
        with patch('tree_sitter_language_pack.downloaded_languages', return_value=[]):
            with caplog.at_level('WARNING', logger=seam.__name__):
                with pytest.raises(seam.GrammarUnavailable) as caught:
                    seam.get_parser('')
        assert caught.value.language == ''
        assert _fetch_warnings(caplog) == []

    def test_uncached_real_grammar_still_announces_the_fetch(self, caplog):
        with patch('tree_sitter_language_pack.downloaded_languages', return_value=[]):
            with caplog.at_level('WARNING', logger=seam.__name__):
                seam.get_parser('python')
        assert _fetch_warnings(caplog) == [
            "tree-sitter grammar for 'python' not yet downloaded — first parse will attempt "
            "to fetch it from the network (see INSTALL.md#network-requirements for offline setups)"]


class TestReferenceScan:
    """The path python-celery's docs/make.bat took: calls ?uncalled -> _drop_referenced."""

    def test_batch_file_is_skipped_silently(self, tmp_path, caplog):
        bat = tmp_path / 'make.bat'
        bat.write_text(MAKE_BAT, encoding='utf-8', newline='\r\n')
        path = str(bat)
        with caplog.at_level('WARNING', logger=seam.__name__):
            referenced = non_python_referenced_names(
                [path], {'': {'help', 'end'}}, {('', 'help'): 1, ('', 'end'): 1},
                {path: {'help': 1, 'end': 1}})
        assert referenced == {}
        assert _fetch_warnings(caplog) == []

    def test_uncached_grammar_of_a_scanned_file_still_warns(self, tmp_path, caplog):
        rb = tmp_path / 'tasks.rb'
        rb.write_text('def back1887_helper; end\ncallback = :back1887_helper\n', encoding='utf-8')
        path = str(rb)
        with patch('tree_sitter_language_pack.downloaded_languages', return_value=[]):
            with caplog.at_level('WARNING', logger=seam.__name__):
                referenced = non_python_referenced_names(
                    [path], {'ruby': {'back1887_helper'}}, {('ruby', 'back1887_helper'): 1},
                    {path: {'back1887_helper': 1}})
        assert referenced == {'ruby': {'back1887_helper'}}
        assert [m.split(' not yet')[0] for m in _fetch_warnings(caplog)] == [
            "tree-sitter grammar for 'ruby'"]
