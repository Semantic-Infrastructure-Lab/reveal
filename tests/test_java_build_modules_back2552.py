"""BACK-2552: a Java type declared in parallel source trees resolves to the copy the importer compiles against.

Guava keeps ``guava/`` and ``android/guava/`` (and test, testlib and GWT twins) in one repository, two Maven
reactors whose modules declare the same fully qualified types. ``_longest_unique_suffix`` declined every
such tie, so scanning the repository root kept 20 of the 2,081 edges a scan of ``guava/`` alone finds, with
only a parse-error warning. Maven modules are now package units (BACK-2559): a dependency names a module by
coordinate, versions and properties are filled as Maven fills them, and a tie goes to the importer's own
module, then to the in-tree modules it depends on. A tie that remains, or a name the importer's build does
not reach, still resolves nowhere.
"""
import json
import textwrap
from pathlib import Path

import pytest

from conftest import _run_reveal_in
from reveal.analyzers.imports import build_cache
from reveal.analyzers.imports.maven import maven_units
from reveal.analyzers.imports.resolution import ProjectResolver


def _pom(artifact, *, version=None, parent=None, group='g', properties=None, deps=(), relative=None):
    head = f'<groupId>{group}</groupId>' if group else ''
    if parent:
        rel = f'<relativePath>{relative}</relativePath>' if relative else ''
        head = f'<parent><groupId>g</groupId><artifactId>{parent[0]}</artifactId><version>{parent[1]}</version>{rel}</parent>'
    props = ''.join(f'<{k}>{v}</{k}>' for k, v in (properties or {}).items())
    dep_xml = ''.join(f'<dependency><groupId>g</groupId><artifactId>{a}</artifactId><version>{v}</version></dependency>'
                      for a, v in deps)
    return (f'<project xmlns="http://maven.apache.org/POM/4.0.0">{head}<artifactId>{artifact}</artifactId>'
            f'{f"<version>{version}</version>" if version else ""}<properties>{props}</properties>'
            f'<dependencies>{dep_xml}</dependencies></project>')


def _java(package, name, *imports):
    lines = [f'package {package};'] + [f'import {i};' for i in imports] + [f'public class {name} {{}}']
    return '\n'.join(lines) + '\n'


def _reactor(flavor):
    parent = ('parent', f'1-{flavor}')
    return {
        f'{flavor}/pom.xml': _pom('parent', version=f'1-{flavor}', parent=('root', '1')),
        f'{flavor}/core/pom.xml': _pom('core', parent=parent, deps=[('util', '${util.version}')]),
        f'{flavor}/core/src/g/base/Pre.java': _java('g.base', 'Pre'),
        f'{flavor}/tests/pom.xml': _pom('tests', parent=parent, deps=[('core', '${project.version}')]),
        f'{flavor}/tests/test/g/base/PreTest.java': _java('g.base', 'PreTest', 'g.base.Pre', 'g.x.Fut'),
    }


TREE = {
    'pom.xml': _pom('root', version='1', properties={'util.version': '1.0'}),
    **_reactor('jre'),
    **_reactor('android'),
    # two releases of one artifact, each declaring g.x.Fut; core takes ${util.version} from the root pom
    'jre/util1/pom.xml': _pom('util', version='1.0'),
    'jre/util1/src/g/x/Fut.java': _java('g.x', 'Fut'),
    'jre/util2/pom.xml': _pom('util', version='2.0'),
    'jre/util2/src/g/x/Fut.java': _java('g.x', 'Fut'),
    # a GWT-style module: its own super-source copy of Pre wins over the dependency's
    'jre/gwt/pom.xml': _pom('gwt', parent=('parent', '1-jre'), deps=[('core', '${project.version}')]),
    'jre/gwt/src/g/Gwt.java': _java('g', 'Gwt', 'g.base.Pre'),
    'jre/gwt/super/g/base/Pre.java': _java('g.base', 'Pre'),
    # two copies inside one module: still a tie
    'dup/pom.xml': _pom('dup', version='1'),
    'dup/a/g/q/Q.java': _java('g.q', 'Q'),
    'dup/b/g/q/Q.java': _java('g.q', 'Q'),
    'dup/src/g/M.java': _java('g', 'M', 'g.q.Q'),
}


def write_tree(root: Path, files=None) -> Path:
    for rel, text in (files or TREE).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(textwrap.dedent(text), encoding='utf-8')
    return root


@pytest.fixture
def repo(tmp_path):
    return write_tree(tmp_path / 'repo')


def _resolved(cwd: Path, target: str = '.'):
    result = _run_reveal_in(cwd, f'imports://{target}', '--format', 'json')
    assert result.returncode == 0, result.stderr
    return {(file, s['module']): s['resolved'] for file, stmts in json.loads(result.stdout)['files'].items()
            for s in stmts}


def test_each_reactor_resolves_to_its_own_copy(repo):
    got = _resolved(repo)
    assert got[('jre/tests/test/g/base/PreTest.java', 'g.base.Pre')] == 'jre/core/src/g/base/Pre.java'
    assert got[('android/tests/test/g/base/PreTest.java', 'g.base.Pre')] == 'android/core/src/g/base/Pre.java'


def test_the_importers_own_module_comes_before_its_dependencies(repo):
    assert _resolved(repo)[('jre/gwt/src/g/Gwt.java', 'g.base.Pre')] == 'jre/gwt/super/g/base/Pre.java'


def test_a_version_property_inherited_from_the_root_pom_picks_the_release(repo):
    """tests -> core -> util:${util.version}, the property set two parents up (tests -> jre -> root)."""
    got = _resolved(repo)
    assert got[('jre/tests/test/g/base/PreTest.java', 'g.x.Fut')] == 'jre/util1/src/g/x/Fut.java'
    assert got[('android/tests/test/g/base/PreTest.java', 'g.x.Fut')] == 'jre/util1/src/g/x/Fut.java'


def test_a_tie_inside_one_module_still_resolves_nowhere(repo):
    assert _resolved(repo)[('dup/src/g/M.java', 'g.q.Q')] is None


def test_without_poms_a_duplicate_type_still_declines(tmp_path):
    root = write_tree(tmp_path / 'plain', {path: text for path, text in TREE.items() if not path.endswith('.xml')})
    got = _resolved(root)
    assert got[('jre/tests/test/g/base/PreTest.java', 'g.base.Pre')] is None


def test_an_unresolvable_version_links_nothing(tmp_path):
    """No guess from groupId and artifactId alone. Guava's shape: guava declares ListenableFuture and depends
    on listenablefuture:${listenablefuture.version} (9999.0-empty, no sources, so its pom is never read); the
    one in-tree listenablefuture (1.0) also declares it. Linking that by name put a second copy on the
    classpath and the importer's tie declined. Here core declares g.x.Fut, ${util.version} is undefined and
    util 1.0 is the only util module: g.x.Fut resolves to core's copy."""
    files = {path: text for path, text in TREE.items() if not path.startswith('jre/util2/')}
    files['pom.xml'] = _pom('root', version='1')
    files['jre/core/src/g/x/Fut.java'] = _java('g.x', 'Fut')
    got = _resolved(write_tree(tmp_path / 'repo', files))
    assert got[('jre/tests/test/g/base/PreTest.java', 'g.x.Fut')] == 'jre/core/src/g/x/Fut.java'


def test_maven_units_fill_coordinates_and_links_as_maven_does(repo):
    root = repo.resolve()
    units = {u.manifest.relative_to(root).as_posix(): u for u in maven_units(sorted(root.rglob('pom.xml')), print)}
    assert units['jre/tests/pom.xml'].name == 'g:tests:1-jre'
    assert units['android/tests/pom.xml'].name == 'g:tests:1-android'
    links = {path: sorted(m.relative_to(root).as_posix() for _n, m in u.local_dependencies) for path, u in units.items()}
    assert links['jre/tests/pom.xml'] == ['jre/core/pom.xml']
    assert links['android/tests/pom.xml'] == ['android/core/pom.xml']
    assert links['jre/core/pom.xml'] == ['jre/util1/pom.xml']


def test_a_pom_that_is_not_xml_declares_nothing(repo):
    (repo / 'jre/tests/pom.xml').write_text('<project><artifactId>tests', encoding='utf-8')
    assert _resolved(repo)[('jre/tests/test/g/base/PreTest.java', 'g.base.Pre')] is None


@pytest.mark.skipif(not hasattr(__import__('os'), 'geteuid') or __import__('os').geteuid() == 0,
                    reason='needs a non-root POSIX user for an unreadable file')
def test_an_unreadable_pom_is_a_recorded_failure(repo):
    pom = repo / 'jre/core/pom.xml'
    pom.chmod(0)
    try:
        failures = []
        ProjectResolver._build_package_model(sorted(repo.rglob('*.java')), on_error=failures.append)
        assert [Path(f.filename).name for f in failures] == ['pom.xml']
    finally:
        pom.chmod(0o644)


# --- cache lifetime: a pom above the scan root is in the graph key (cause 6) --------------------------------

def _fut_in_jre(repo: Path):
    return _resolved(repo / 'jre')[('tests/test/g/base/PreTest.java', 'g.x.Fut')]


def _bump_util_version(repo: Path):
    (repo / 'pom.xml').write_text(_pom('root', version='1', properties={'util.version': '2.0'}), encoding='utf-8')


@pytest.fixture
def cached(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')


@pytest.mark.disk_cache
def test_cache_off_answer_moves_with_the_pom_above_the_root(repo, monkeypatch):
    """Positive control for the cached tests below."""
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    assert _fut_in_jre(repo) == 'util1/src/g/x/Fut.java'
    _bump_util_version(repo)
    assert _fut_in_jre(repo) == 'util2/src/g/x/Fut.java'


@pytest.mark.disk_cache
def test_an_edit_to_a_pom_above_the_scan_root_misses_the_graph_cache(repo, cached):
    assert _fut_in_jre(repo) == 'util1/src/g/x/Fut.java'
    assert _fut_in_jre(repo) == 'util1/src/g/x/Fut.java'   # warm
    _bump_util_version(repo)
    assert _fut_in_jre(repo) == 'util2/src/g/x/Fut.java'


@pytest.mark.disk_cache
def test_without_the_context_manifests_the_cached_graph_goes_stale(repo, cached, monkeypatch):
    """Red control: a key without the manifests above the root serves the old graph after the edit."""
    monkeypatch.setattr(build_cache, '_context_manifests', lambda root: [])
    assert _fut_in_jre(repo) == 'util1/src/g/x/Fut.java'
    _bump_util_version(repo)
    assert _fut_in_jre(repo) == 'util1/src/g/x/Fut.java'
