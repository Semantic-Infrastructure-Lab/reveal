"""BACK-2087: every answer ranked by the import graph states the rule it counted by.

``imports://`` and ``depends://`` print the edge rule (``edge_rule`` in JSON, a ``Rule:`` line in
text, built by ``service.edge_rule``). After BACK-2077 the graph keeps function-level imports, so
``architecture://``, ``overview://``, ``pack`` and ``architecture --against`` (which call the same
formatters or read the same graph) count them too: ``late.py`` below is imported only inside a
function, and its fan-in of 1 exists only because the rule counts that edge. None of those
answers said so (ground rule 4: every number states its rule).

The fixture: ``core`` is imported by ``eager`` (module level), ``lazy`` (inside a function) and a
test file; ``late`` only inside ``lazy``'s function; ``ring_a -> ring_b`` is module level and
``ring_b -> ring_a`` function level (a cycle only if function-level imports are counted).
Entry points ignore importers under a test path and cycles leave function-level imports out, so
those two sections carry their own rule beside the headline one (``edge_rule_sections``).
"""

import json
import subprocess

import pytest

from conftest import _run_reveal_direct
from reveal.utils.path_utils import to_posix

FILES = {
    'pyproject.toml': '[project]\nname = "probe"\n',
    'core.py': 'X = 1\n',
    'eager.py': 'import core\n',
    'lazy.py': 'def f():\n    import core\n    import late\n    return core.X + late.Y\n',
    'late.py': 'Y = 2\n',
    'ring_a.py': 'import ring_b\n',
    'ring_b.py': 'def f():\n    import ring_a\n    return ring_a\n',
    'tests/test_core.py': 'import core\n',
}

MIXED = {
    'pyproject.toml': '[project]\nname = "probe"\n',
    'a.rb': 'X = 1\n',
    'b.rb': "require_relative 'a'\n",
}

HEADLINE = {'lazy': 'include', 'lazy_default': True, 'type_checking': 'excluded',
            'tests': 'included', 'scope': 'scanned_path', 'unclassified_edges': 0}
ENTRY_POINTS = {'lazy': 'include', 'lazy_default': True, 'tests': 'importers_not_counted'}
CYCLES = {'lazy': 'exclude', 'lazy_default': True, 'tests': 'included'}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')


def _tree(root, files):
    root.mkdir()
    root = root.resolve()  # macOS tmp is /private/var
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


@pytest.fixture
def project(tmp_path):
    return _tree(tmp_path / 'p', FILES)


def _run(*args):
    out = _run_reveal_direct(*args)
    assert out.returncode == 0, out.stderr
    return out.stdout


def _json(*args):
    return json.loads(_run(*args, '--format', 'json'))


def _imports_rule(root, query):
    """The rule imports:// prints for the same view: the consumer must carry this object. The
    consumers resolve at the requested path, which imports:// spells &scope=path (BACK-1054)."""
    return _json(f'imports://{to_posix(root)}?{query}&scope=path')['edge_rule']


def _assert_rule(rule, expected):
    for key, value in expected.items():
        assert rule[key] == value, (key, rule)


# imports://'s own rule fields (BACK-1054): where it resolved and with which &scope/&tests. A
# composing command takes none of those parameters and prints none of them.
RESOLUTION_KEYS = {'root', 'root_source', 'scope_param', 'tests_param', 'via', 'ungated_languages', 'ungated_edges',
                   'outside_root_edges'}


def _same_rule(rule, imports_rule, noun):
    """The rule is imports://'s for the same view, built by the same function. Only the pointer
    at the other views differs: this command takes no &lazy, so it must not point at one."""
    assert not RESOLUTION_KEYS & set(rule)
    assert {k: v for k, v in rule.items() if k != 'text'} == {
        k: v for k, v in imports_rule.items() if k != 'text' and k not in RESOLUTION_KEYS}
    assert rule['text'].partition(' (default); ')[0] == imports_rule['text'].partition(' (default); ')[0]
    assert f'{noun} takes no &lazy' in rule['text'] and 'other views: &lazy=' not in rule['text']


def _assert_rules(owner, root, noun='architecture://'):
    """Headline = fan-in view; entry points and cycles carry their own; all equal imports://'s."""
    _same_rule(owner['edge_rule'], _imports_rule(root, 'rank=fan-in'), noun)
    _assert_rule(owner['edge_rule'], HEADLINE)
    sections = owner['edge_rule_sections']
    assert sorted(sections) == ['cycles', 'entry_points']
    _same_rule(sections['entry_points'], _imports_rule(root, 'entrypoints'), noun)
    _same_rule(sections['cycles'], _imports_rule(root, 'circular'), noun)
    _assert_rule(sections['entry_points'], ENTRY_POINTS)
    _assert_rule(sections['cycles'], CYCLES)


def _assert_rule_lines(text):
    assert 'Rule: ' in text and 'function-level (lazy) imports included (default)' in text
    assert 'TYPE_CHECKING imports excluded' in text
    assert 'Rule (entry points): ' in text and 'importers under a test path not counted' in text
    assert 'Rule (cycles): ' in text and 'function-level (lazy) imports excluded (default)' in text


# ------------------------------------------------------------------ architecture://

def test_architecture_states_its_rule_in_json(project):
    data = _json(f'architecture://{to_posix(project)}')
    facts = data['facts']
    core = {to_posix(e['file']).rsplit('/', 1)[-1]: e['fan_in'] for e in facts['core_abstractions']}
    # core: eager + lazy (function level) + the test file; late exists only through the lazy edge.
    assert core == {'core.py': 3, 'late.py': 1, 'ring_a.py': 1, 'ring_b.py': 1}
    assert facts['circular_groups'] == []  # the ring is a cycle only with function-level imports
    _assert_rules(data, project)


def test_architecture_states_its_rule_in_text(project):
    _assert_rule_lines(_run(f'architecture://{to_posix(project)}'))


def test_architecture_without_imports_states_no_rule(project):
    """Negative control: no edge was counted, so no rule is claimed."""
    data = _json(f'architecture://{to_posix(project)}?no_imports=true')
    assert 'edge_rule' not in data and 'edge_rule_sections' not in data
    assert 'Rule' not in _run(f'architecture://{to_posix(project)}?no_imports=true')


def test_architecture_names_a_language_whose_scope_is_not_recorded(tmp_path):
    root = _tree(tmp_path / 'mixed', MIXED)
    data = _json(f'architecture://{to_posix(root)}')
    assert [e['fan_in'] for e in data['facts']['core_abstractions']] == [1]
    assert data['edge_rule']['unclassified_edges'] == 1
    assert data['edge_rule']['unclassified_languages'] == ['ruby']
    assert 'Import scope is not recorded for ruby: 1 edge(s)' in _run(f'architecture://{to_posix(root)}')


# ------------------------------------------------------------------ overview://

def test_overview_states_its_rule_in_json(project):
    data = _json(f'overview://{to_posix(project)}?no_git=true')
    arch = data['architecture']
    fan_in = {to_posix(e['file']).rsplit('/', 1)[-1]: e['fan_in'] for e in arch['fan_in'] if e['fan_in']}
    assert fan_in == {'core.py': 3, 'late.py': 1, 'ring_a.py': 1, 'ring_b.py': 1}
    assert arch['circular_count'] == 0
    _assert_rules(arch, project, 'overview://')


def test_overview_states_its_rule_in_text(project):
    _assert_rule_lines(_run(f'overview://{to_posix(project)}?no_git=true'))


def test_overview_without_imports_states_no_rule(project):
    data = _json(f'overview://{to_posix(project)}?no_git=true&no_imports=true')
    assert 'edge_rule' not in data['architecture']
    assert 'Rule' not in _run(f'overview://{to_posix(project)}?no_git=true&no_imports=true')


# ------------------------------------------------------------------ pack

def test_pack_architecture_states_its_rule(project):
    data = _json('pack', to_posix(project), '--architecture')
    fan_in = {f['relative']: f['fan_in'] for f in data['files'] if f['fan_in']}
    assert fan_in == {'core.py': 3, 'late.py': 1, 'ring_a.py': 1, 'ring_b.py': 1}
    # imports://'s object for the same view; pack names its own subject and cannot take &lazy.
    # pack builds its rule from the graph alone (_pack_edge_rule): the keys it carries are imports://'s.
    imports_rule = _imports_rule(project, 'rank=fan-in')
    assert {k: v for k, v in data['edge_rule'].items() if k != 'text'} == {
        k: imports_rule[k] for k in data['edge_rule'] if k != 'text'}
    _assert_rule(data['edge_rule'], HEADLINE)
    assert 'fan-in' in data['edge_rule']['text'] and 'pack takes no &lazy' in data['edge_rule']['text']
    text = _run('pack', to_posix(project), '--architecture')
    assert 'Rule: ' in text and 'function-level (lazy) imports included (default)' in text


def test_pack_focus_states_its_rule(project):
    """--focus ranks by a walk over the same edges: the rule names relevance, not fan-in."""
    data = _json('pack', to_posix(project), '--focus', 'late')
    _assert_rule(data['edge_rule'], HEADLINE)
    assert 'relevance' in data['edge_rule']['text']
    assert 'Rule: ' in _run('pack', to_posix(project), '--focus', 'late')


def test_pack_without_graph_flags_states_no_rule(project):
    """Negative control: no import edge ranked anything."""
    assert 'edge_rule' not in _json('pack', to_posix(project))
    assert 'Rule: ' not in _run('pack', to_posix(project))


def test_pack_over_mcp_states_its_rule(project):
    from reveal.mcp_server import reveal_pack
    text = reveal_pack(str(project), architecture=True)
    assert 'Rule: fan-in counts' in text and 'function-level (lazy) imports included (default)' in text
    assert 'Rule: ' not in reveal_pack(str(project))


# ------------------------------------------------------------------ deps

def test_deps_text_states_the_cycle_rule(project):
    """deps:// reports 'no circular deps' from the load-time view; its JSON said so, its text did not."""
    data = _json(f'deps://{to_posix(project)}')
    _same_rule(data['circular']['edge_rule'], _imports_rule(project, 'circular'), 'deps://')
    text = _run(f'deps://{to_posix(project)}')
    assert 'no circular deps' in text
    assert 'Rule: ' in text and 'function-level (lazy) imports excluded (default)' in text
    assert 'deps:// takes no &lazy' in text


# ------------------------------------------------------------------ architecture --against

def _git(root, *args):
    subprocess.run(['git', *args], cwd=str(root), check=True, timeout=60, capture_output=True)


def test_architecture_against_states_its_rule(tmp_path):
    root = _tree(tmp_path / 'repo', {k: v for k, v in FILES.items() if k != 'tests/test_core.py'})
    (root / 'lazy.py').write_text('def f():\n    import core\n    return core.X\n', encoding='utf-8')
    _git(root, 'init', '-q')
    _git(root, 'add', '.')
    _git(root, '-c', 'commit.gpgsign=false', '-c', 'user.name=t', '-c', 'user.email=t@example.com', 'commit', '-q', '-m', 'base')
    (root / 'lazy.py').write_text(FILES['lazy.py'], encoding='utf-8')  # the function-level edge to late
    data = _json(f'architecture://{to_posix(root)}?against=HEAD')
    assert data['type'] == 'architecture_diff'
    late = [d for d in data['deltas']['fan_in'] if d['file'].endswith('late.py')]
    assert [(d['base'], d['head']) for d in late] == [(0, 1)]  # the delta is the lazy edge
    _assert_rules(data, root)


def test_architecture_against_states_its_rule_in_text(tmp_path):
    root = _tree(tmp_path / 'repo', {k: v for k, v in FILES.items() if k != 'tests/test_core.py'})
    (root / 'lazy.py').write_text('def f():\n    import core\n    return core.X\n', encoding='utf-8')
    _git(root, 'init', '-q')
    _git(root, 'add', '.')
    _git(root, '-c', 'commit.gpgsign=false', '-c', 'user.name=t', '-c', 'user.email=t@example.com',
         'commit', '-q', '-m', 'base')
    (root / 'lazy.py').write_text(FILES['lazy.py'], encoding='utf-8')
    text = _run(f'architecture://{to_posix(root)}?against=HEAD')
    assert 'late.py' in text and 'Fan-in changes' in text
    _assert_rule_lines(text)
