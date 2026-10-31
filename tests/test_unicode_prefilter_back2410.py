"""A prefilter must not reject a match accepted by the decoded body owner."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from reveal import api
from reveal.utils import parallel


@pytest.mark.parametrize('body,term,expected', [
    ('CAFÉ', 'café', True), ('Kelvin', 'kelvin', True), ('ΟΣ', 'ος', True),
    ('İstanbul', 'i\u0307stanbul', True), ('NEEDLE', 'needle', True),
    ('unrelated', 'needle', False), ('Straße', 'STRASSE', False),
    ('cafe\u0301', 'café', False),
])
@pytest.mark.parametrize('pooled', [False, True])
def test_unicode_match_and_nonmatch_decisions(tmp_path, body, term, expected, pooled):
    paths = [tmp_path / f'{i}.md' for i in range(8 if pooled else 1)]
    for path in paths:
        path.write_text(body, encoding='utf-8')
    found = parallel.grep_files(paths, term, workers=2)
    assert found == (paths if expected else [])
    assert found.lost == [] and found.unreadable == []


@pytest.mark.parametrize('aggregate', [False, True])
def test_markdown_modes_match_decoded_unicode_and_retain_loss(tmp_path, aggregate):
    (tmp_path / 'good.md').write_text('---\ntitle: guide\n---\nCAFÉ\n', encoding='utf-8')
    request = f'markdown://{tmp_path.as_posix()}?body-contains=café'
    if aggregate:
        request += '&aggregate=title'
    answer = api.query(request)
    assert answer['matched_files'] == 1
    if aggregate:
        assert answer['aggregate'] == [{'value': 'guide', 'count': 1}]
    (tmp_path / 'bad.md').write_bytes(b'caf\xe9')
    failed = api.query(request)
    assert failed['matched_files'] == 1
    assert any(w['type'] == 'unreadable_files' for w in failed['meta']['warnings'])


def test_incidental_accelerator_cannot_break_ascii_scan(tmp_path):
    path = tmp_path / 'one.md'
    path.write_bytes(b'needle')
    code = '''
import json,sys,types
sys.modules['stringzilla'] = types.SimpleNamespace(Str=lambda data: object())
from reveal.utils.parallel import grep_files
print(json.dumps([str(p) for p in grep_files([__import__('pathlib').Path(sys.argv[1])], 'needle')]))
'''
    run = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True,
                         text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == [str(path)]


def test_multi_term_and_still_requires_every_term(tmp_path):
    path = tmp_path / 'one.md'
    path.write_text('CAFÉ tea', encoding='utf-8')
    assert parallel.grep_files([path], ['café', 'tea']) == [path]
    assert parallel.grep_files([path], ['café', 'absent']) == []
