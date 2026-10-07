"""A recovered parse must not carry the trust metadata of a clean one (BACK-1729).

BACK-1589 made every format analyzer that overrides get_structure set `_has_errors` when
tree-sitter recovered around a syntax error, and the file view turns that into the
"Parse recovered" notice and JSON `meta.parse_recovered`. The override's own `meta` is
left as written for a valid file: `parse_mode: tree_sitter_full`, `confidence: 1.0`. So
`reveal broken.tf --format json` says `parse_recovered: true` and, in the same document,
`structure.meta.confidence: 1.0`. The contract's value for this state is
`tree_sitter_partial` ("parsed but some nodes are ERROR nodes", CONTRACT_VERSIONS.md),
and the one analyzer that lowers its own confidence on bad input uses 0.5 (jsonl).

The owner is the BACK-1589 wrapper (TreeSitterAnalyzer.__init_subclass__ in
reveal/treesitter.py), which sees every override; `_recovered_trust` there rewrites the
meta. The private `_has_errors` key also reached the JSON payload next to the public
`meta.parse_recovered`; `_enrich_structure` (reveal/display/structure.py) drops it. The NginxAnalyzer named
in the task never sets `_has_errors` (it is a line parser), so it cannot leak it.
"""
import json
import os
import subprocess
import sys

import pytest

import reveal.analyzers  # noqa: F401  (registers every analyzer)
from reveal.registry import get_analyzer
from test_parse_recovery_disclosed_back1589 import CASES, _structure

pytestmark = [pytest.mark.component]

IDS = [c[0] for c in CASES]
# Dockerfile's recovered structure has no meta at all, so it states no trust to correct.
WITH_META = [c for c in CASES if c[0] != 'Dockerfile']


@pytest.fixture(autouse=True)
def no_disk_cache(monkeypatch):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')


def _trust(structure):
    meta = structure.get('meta') or {}
    return meta.get('parse_mode'), meta.get('confidence')


@pytest.mark.parametrize('name,broken,valid', CASES, ids=IDS)
def test_a_valid_file_keeps_full_trust(tmp_path, name, broken, valid):
    """Negative control: nothing changes for a clean parse."""
    structure = _structure(tmp_path, name, valid)
    assert not structure.get('_has_errors')
    assert _trust(structure) == ('tree_sitter_full', 1.0)


@pytest.mark.parametrize('name,broken,valid', WITH_META, ids=[c[0] for c in WITH_META])
def test_a_recovered_parse_lowers_its_own_trust(tmp_path, name, broken, valid):
    structure = _structure(tmp_path, name, broken)
    assert structure.get('_has_errors') is True, 'precondition: the parse was recovered'
    parse_mode, confidence = _trust(structure)
    assert parse_mode == 'tree_sitter_partial'
    assert confidence < 1.0


def _reveal_json(cwd, *argv):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', REVEAL_NO_UPDATE_CHECK='1',
               REVEAL_DISK_CACHE='0')
    proc = subprocess.run([sys.executable, '-m', 'reveal', *argv, '--format', 'json'],
                          cwd=cwd, env=env, capture_output=True, text=True,
                          encoding='utf-8', timeout=120)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# The task's own repro: a .tf file with a trailing `resource = = =`.
HCL_BROKEN = 'variable "region" {\n  default = "x"\n}\n\nresource = = =\n'
HCL_VALID = 'variable "region" {\n  default = "x"\n}\n'


def test_the_json_document_does_not_contradict_itself(tmp_path):
    (tmp_path / 'main.tf').write_text(HCL_BROKEN, encoding='utf-8')
    result = _reveal_json(tmp_path, 'main.tf')
    assert result['meta'].get('parse_recovered') is True, 'precondition'
    assert result['structure']['meta']['confidence'] < 1.0


def test_the_private_flag_stays_out_of_the_json_payload(tmp_path):
    (tmp_path / 'main.tf').write_text(HCL_BROKEN, encoding='utf-8')
    result = _reveal_json(tmp_path, 'main.tf')
    assert result['meta'].get('parse_recovered') is True, 'precondition'
    assert '_has_errors' not in result['structure']


def test_a_clean_hcl_file_says_nothing_about_recovery(tmp_path):
    (tmp_path / 'main.tf').write_text(HCL_VALID, encoding='utf-8')
    result = _reveal_json(tmp_path, 'main.tf')
    assert 'parse_recovered' not in result['meta']
    assert '_has_errors' not in result['structure']
    assert result['structure']['meta']['confidence'] == 1.0


def test_nginx_never_sets_the_private_flag(tmp_path):
    """The task's nginx premise, measured: unterminated, over-closed and unquoted shapes."""
    shapes = ['server {\n    listen 80;\n    location / {\n        return 200;\n',
              'server {\n    listen 80;\n}\n}\n}\n',
              'server {\n    listen 80\n    server_name "open;\n}\n']
    for i, text in enumerate(shapes):
        path = tmp_path / ('site%d.conf' % i)
        path.write_text(text, encoding='utf-8')
        analyzer = get_analyzer(str(path))(str(path))
        assert type(analyzer).__name__ == 'NginxAnalyzer', 'precondition'
        assert '_has_errors' not in analyzer.get_structure()
