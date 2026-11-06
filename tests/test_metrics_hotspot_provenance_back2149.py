"""BACK-2149 S3: each metrics `hotspots[]` entry carries the path-only provenance tag.

The tag is ``provenance_for_display_path`` over the entry's file relative to the scan target: ``'test'``,
``'vendor'``, ``'minified'`` or ``None`` for first party, the vocabulary the hotspots noun's
``file_hotspots[].provenance`` used (not ``?view=provenance``'s ``'first_party'``). It must not depend on
how the target is spelled: the project below sits under an ancestor directory named ``tests``, which a
classification of the spelled path instead of the path under the scan root would tag ``'test'``.
"""
import json
import os

import pytest

from conftest import _run_reveal_direct as run

pytestmark = pytest.mark.component

# One long function per file makes each a ranked hotspot (score 5); the content does not decide the tag.
HOTSPOT = {
    '.py': 'def long0():\n' + ''.join(f'    v{i} = {i}\n' for i in range(130)) + '    return v0\n',
    '.js': 'function long0() {\n' + ''.join(f'  var v{i} = {i};\n' for i in range(130)) + '  return v0;\n}\n',
}
FILES = {
    'src/core.py': None,
    'tests/test_core.py': 'test',
    'vendor/lib.py': 'vendor',
    'static/app.min.js': 'minified',
}


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / 'tests' / 'proj'
    for rel in FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(HOTSPOT[path.suffix], encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    return root


def _tags(*argv):
    result = run(*argv, '--format', 'json', '--no-gitignore')
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    return {entry['file']: entry['provenance'] for entry in doc['hotspots']}


def test_every_hotspot_entry_carries_its_path_only_tag(project):
    assert _tags('metrics', 'tests/proj', '--hotspots', '--top', '0') == FILES


@pytest.mark.parametrize('spelling', ['relative-from-root', 'inside', 'dot-slash', 'absolute'])
@pytest.mark.parametrize('transport', ['cli', 'uri'])
def test_the_tag_does_not_depend_on_how_the_target_is_spelled(project, monkeypatch, spelling, transport):
    target = {'relative-from-root': 'tests/proj', 'inside': '.', 'dot-slash': './tests/proj',
              'absolute': str(project)}[spelling]
    if spelling == 'inside':
        monkeypatch.chdir(project)
    if transport == 'uri' and spelling == 'absolute':
        target = project.as_posix()
    argv = (['metrics', target, '--hotspots', '--top', '0'] if transport == 'cli'
            else [f'metrics://{target}?hotspots=true&top=0'])
    assert _tags(*argv) == FILES


def test_a_single_file_target_is_tagged_from_its_own_name(project):
    """The display path of a file target is its name, so an ancestor `tests/` does not make it a test."""
    assert _tags('metrics', os.path.join('tests', 'proj', 'src', 'core.py'), '--hotspots') == {'core.py': None}
    assert _tags('metrics', os.path.join('tests', 'proj', 'tests', 'test_core.py'), '--hotspots') == {
        'test_core.py': 'test'}


def test_the_tag_agrees_with_the_hotspots_nouns_file_tag(project):
    """Negative control on the sibling that had it: hotspots' file_hotspots[].provenance is unchanged and equal."""
    result = run('hotspots', 'tests/proj', '--files-only', '--top', '0', '--format', 'json', '--no-gitignore')
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout)
    assert {entry['file']: entry['provenance'] for entry in doc['file_hotspots']} == FILES


def test_the_page_and_the_view_keep_their_own_shapes(project):
    """Only hotspots[] entries gain the tag: files[] rows and the provenance view are unchanged."""
    result = run('metrics', 'tests/proj', '--hotspots', '--format', 'json', '--no-gitignore')
    doc = json.loads(result.stdout)
    assert all('provenance' not in row for row in doc['files'])
    view = json.loads(run('metrics', 'tests/proj', '--view', 'provenance', '--format', 'json',
                          '--no-gitignore').stdout)
    assert {row['file']: row['provenance'] for row in view['files']}['src/core.py'] == 'first_party'
