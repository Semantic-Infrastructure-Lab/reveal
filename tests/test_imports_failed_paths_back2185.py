"""imports' failure disclosures spell their files as the answer's rows are spelled, not as host paths (BACK-2185).

``metadata.files_failed`` and ``metadata.files_lost`` were ``str(path)`` of the absolute walk paths, and
``metadata.extraction_diagnostics`` and the ``analysis_incomplete`` warning's ``directories`` fell back to
the host path for anything outside the requested path; under the default ``&scope=root`` the walk covers
the whole project, so asking about ``src/`` disclosed ``/home/<user>/.../other/bad.js``. Every one is now
spelled from the requested directory, as the rows are (BACK-2183/2184), and the text summary lists the
same strings. ``get_metadata()`` itself keeps absolute paths: overview:// and the architecture diff read
it as a library and spell it against their own base.
"""
import json
import os
from pathlib import Path

from conftest import _run_reveal_in
from reveal.adapters.imports import ImportsAdapter


def _project(tmp_path):
    """Two files tree-sitter parses with errors: one in the requested src/, one beside it."""
    proj = tmp_path / 'proj'
    (proj / 'src').mkdir(parents=True)
    (proj / 'other').mkdir()
    (proj / 'package.json').write_text('{"name": "p"}\n', encoding='utf-8')
    (proj / 'src' / 'a.js').write_text("import x from './b';\n", encoding='utf-8')
    (proj / 'src' / 'b.js').write_text('export default 1;\n', encoding='utf-8')
    (proj / 'src' / 'bad.js').write_text("import y from './b';\nconst = = ;\n", encoding='utf-8')
    (proj / 'other' / 'bad.js').write_text("import y from './c';\nfunction (((( {{{\n", encoding='utf-8')
    return proj


def _run(tmp_path, uri, *args):
    result = _run_reveal_in(tmp_path, uri, *args)
    assert result.returncode == 3, (uri, result.stderr)  # a partial answer: files parsed with errors
    assert str(tmp_path) not in result.stdout and tmp_path.as_posix() not in result.stdout, (uri, result.stdout)
    return result.stdout


def _metadata(tmp_path, uri):
    return json.loads(_run(tmp_path, uri, '--format', 'json'))['metadata']


def test_files_failed_and_diagnostics_are_spelled_from_the_requested_directory(tmp_path):
    _project(tmp_path)
    metadata = _metadata(tmp_path, 'imports://proj/src')
    assert metadata['files_failed_count'] == 2
    assert metadata['files_failed'] == ['../other/bad.js', 'bad.js']
    assert sorted(metadata['extraction_diagnostics']) == ['../other/bad.js', 'bad.js']


def test_a_file_target_spells_failed_files_from_its_directory(tmp_path):
    _project(tmp_path)
    metadata = _metadata(tmp_path, 'imports://proj/src/a.js')
    assert metadata['files_failed'] == ['../other/bad.js', 'bad.js']
    assert sorted(metadata['extraction_diagnostics']) == ['../other/bad.js', 'bad.js']


def test_the_text_summary_lists_the_same_spelling(tmp_path):
    _project(tmp_path)
    stdout = _run(tmp_path, 'imports://proj/src')
    assert '      - ../other/bad.js' in stdout and '      - bad.js' in stdout


def test_files_lost_and_a_windows_spelling_reach_the_answer_with_forward_slashes(tmp_path, monkeypatch):
    """A file a dead pool worker took cannot be produced on demand, and Linux cannot spell a path the
    Windows way, so the metadata the view reads is handed both (BACK-2188 control): an absolute lost
    file beside the path and a relative one spelled with backslashes."""
    proj = _project(tmp_path)
    real = ImportsAdapter.get_metadata
    lost = str(proj / 'other' / 'lost.js')

    def with_lost(self):
        metadata = real(self)
        metadata.update(files_lost=[lost], files_lost_count=1, files_failed_count=metadata['files_failed_count'] + 2,
                        files_failed=sorted(metadata['files_failed'] + [lost, 'deep\\win.js']))
        return metadata

    monkeypatch.setattr(ImportsAdapter, 'get_metadata', with_lost)
    metadata = _metadata(tmp_path, 'imports://proj/src')
    assert metadata['files_lost'] == ['../other/lost.js']
    assert sorted(metadata['files_failed']) == ['../other/bad.js', '../other/lost.js', 'bad.js', 'deep/win.js']


def test_a_failed_directory_outside_the_path_is_spelled_relative(tmp_path, monkeypatch):
    """The walk covers the project root; a directory it could not list beside src/ is named ../other.
    (The OSError text in ``causes`` and the message is the walker's and still carries its path: a
    separate, cross-adapter finding, so only the spelled fields are asserted here.)"""
    proj = _project(tmp_path)
    denied = (proj / 'other').resolve()
    real = os.scandir

    def scandir(directory):
        if Path(directory).resolve() == denied:
            raise PermissionError(13, 'controlled directory loss', str(denied))
        return real(directory)

    monkeypatch.setattr(os, 'scandir', scandir)
    result = _run_reveal_in(tmp_path, 'imports://proj/src', '--format', 'json')
    assert result.returncode == 3, result.stderr
    warnings = [w for w in json.loads(result.stdout)['meta']['warnings'] if w.get('type') == 'analysis_incomplete']
    assert [w['directories'] for w in warnings] == [['../other']]
    assert warnings[0]['message'].startswith('1 identified directory enumeration(s) failed; missing file population '
                                             'is unknown: ../other (PermissionError')


def test_the_library_metadata_keeps_absolute_paths(tmp_path):
    """Negative control: get_metadata() is read by overview:// and the architecture diff, which spell it
    against their own base; it stays absolute."""
    proj = _project(tmp_path)
    adapter = ImportsAdapter(str(proj / 'src'))
    adapter.get_structure()
    failed = adapter.get_metadata()['files_failed']
    assert failed == sorted(str((proj / sub / 'bad.js').resolve()) for sub in ('other', 'src'))
