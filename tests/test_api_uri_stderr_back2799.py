"""``api.query``'s URI form prints nothing, as its noun form does (BACK-2799, D21).

The Python API returns the CLI's JSON document (or raises with it), so a diagnostic belongs in the answer, never on the
caller's stderr: the noun form says so (``answer_is_json(True)`` inside its invocation, as ``--format json`` does on the
CLI), and a per-file line such as ``Warning: Failed to analyze F: ...`` is then not printed. The URI form opened its
invocation log without saying the answer is JSON, so ``api.query('ast://bad.xml')`` printed that line on stderr.
Captured at the file descriptor (``capfd``), so a print to ``sys.stderr`` and a logging handler are both seen.
"""
import pytest

from reveal import api
from reveal.errors import AnalysisFailedError

BAD_XML = '<root'


@pytest.fixture
def bad(tmp_path, monkeypatch):
    (tmp_path / 'bad.xml').write_text(BAD_XML, encoding='utf-8')
    (tmp_path / 'proj').mkdir()
    (tmp_path / 'proj' / 'app.py').write_text('def main():\n    return 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize('call', [lambda: api.query('ast://bad.xml'), lambda: api.query('ast', 'bad.xml')],
                         ids=['uri', 'noun'])
def test_a_failed_analysis_raises_and_prints_nothing(bad, capfd, call):
    with pytest.raises(AnalysisFailedError) as caught:
        call()
    assert 'bad.xml' in str(caught.value)
    out, err = capfd.readouterr()
    assert (out, err) == ('', '')


@pytest.mark.parametrize('call', [lambda: api.query('ast://proj'), lambda: api.query('ast', 'proj')],
                         ids=['uri', 'noun'])
def test_a_clean_answer_prints_nothing(bad, capfd, call):
    assert call()['type'] == 'ast_query'
    assert capfd.readouterr() == ('', '')
