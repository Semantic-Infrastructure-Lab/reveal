"""The conformance fixture (test_vocabulary_conformance_back2654 ``workspace``) with lists long enough to show a cut:
cross-calling modules, tests that patch them, four more commits, three Markdown documents and a five-row JSON array
(BACK-2673: --head/--tail/--range and the hotspot caps)."""
import json

import pytest

from test_vocabulary_conformance_back2654 import workspace  # noqa: F401  (fixture)

MODULES = {
    'mod_a.py': 'import os\nfrom mod_b import helper_b\n\n\ndef helper_a(x):\n    if x:\n        return helper_b(x)\n'
                '    return os.getcwd()\n\n\ndef unused_a():\n    return 1\n\n\ndef twice_a(x):\n    return helper_a(x) + helper_a(x)\n',
    'mod_b.py': 'import json\nfrom mod_c import helper_c\n\n\ndef helper_b(x):\n    for i in range(3):\n        if i == x:\n'
                '            return helper_c(i)\n    return json.dumps(x)\n',
    'mod_c.py': 'import sys\n\n\ndef helper_c(x):\n    if x > 1:\n        return sys.platform\n    elif x < 0:\n'
                '        return None\n    return x\n',
    'mod_d.py': 'from mod_a import helper_a, twice_a\nfrom app import serve\n\n\ndef run(x):\n    serve(x)\n'
                '    return helper_a(x) or twice_a(x)\n',
    'mod_e.py': 'import os\nimport socket\nimport subprocess\nimport time\n' + ''.join(
        f'\n\ndef io_{n}(path):\n    with open(path) as handle:\n        data = handle.read()\n    os.environ.get("X")\n'
        f'    time.time()\n    subprocess.run(["true"])\n    socket.gethostname()\n    return data\n'
        for n in ('one', 'two', 'three')),
}
TESTS = {
    'tests/test_mods.py': 'from unittest import mock\nimport mod_a\nimport mod_b\nimport mod_d\n\n\n'
                          '@mock.patch("mod_a.helper_b")\n@mock.patch("mod_b.helper_c")\ndef test_a(hc, hb):\n'
                          '    assert mod_a.helper_a(1) is not None\n\n\n'
                          'def test_b(monkeypatch):\n    monkeypatch.setattr(mod_b, "helper_c", lambda i: i)\n'
                          '    monkeypatch.setattr("mod_d.serve", lambda x: None)\n    assert mod_b.helper_b(1) == 1\n',
    'tests/test_io.py': 'from unittest import mock\nimport mod_e\n\n' + ''.join(
        f'@mock.patch("mod_e.subprocess.run")\n@mock.patch("mod_e.time.time")\n@mock.patch("mod_e.socket.gethostname")\n'
        f'@mock.patch("mod_e.open", create=True)\ndef test_{n}(o, h, t, r):\n    mod_e.io_{n}("x")\n\n\n'
        for n in ('one', 'two', 'three')),
}
DOCS = {f'doc_{n}.md': f'---\ntitle: Doc {n}\nn: {n}\n---\n# Doc {n}\n\nSee [guide](guide.md).\n' for n in (1, 2, 3)}


def enrich(root):
    """Add the files to the fixture project and commit them in four more commits."""
    import pygit2
    for name, text in {**MODULES, **TESTS, **DOCS}.items():
        (root / name).write_text(text, encoding='utf-8')
    (root / 'rows.json').write_text(json.dumps([{'name': c, 'n': i} for i, c in enumerate('abcde')]), encoding='utf-8')
    repo = pygit2.Repository(str(root))
    groups = (['mod_a.py', 'mod_b.py'], ['mod_c.py', 'mod_d.py', 'mod_e.py', *TESTS], ['guide.md', 'rows.json', *DOCS])
    for i, group in enumerate(groups):
        for name in group:
            repo.index.add(name)
        repo.index.write()
        signature = pygit2.Signature('Fixture', 'fixture@example.com', 1700000000 + 3600 * (i + 1), 0)
        repo.create_commit('HEAD', signature, signature, f'commit {i}', repo.index.write_tree(), [repo.head.target])


@pytest.fixture
def rich(workspace):  # noqa: F811
    """The enriched project; the current directory holds ``proj``, Claude's and Codex's homes."""
    enrich(workspace.parent.parent / 'proj')
    return workspace.parent.parent
