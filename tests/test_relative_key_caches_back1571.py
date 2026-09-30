"""BACK-1571: process-lifetime caches keyed by a relative path answered for the first cwd.

Same shape as BACK-1568's _cached_resolve: 'src' or './s.yaml' named a different directory
or file after a chdir (the test suite, a reveal.api host), and the cache returned the first
one's answer. Each case asks the same relative question in two projects.
"""
import json

from reveal.analyzers.imports import javascript
from reveal.schemas.frontmatter import SchemaLoader


def _two_projects(tmp_path, write):
    projects = []
    for name in ('first', 'second'):
        root = tmp_path / name
        root.mkdir()
        write(root, name)
        projects.append(root)
    return projects


def test_tsconfig_lookup_follows_the_cwd(tmp_path, monkeypatch):
    def write(root, name):
        (root / 'src').mkdir()
        (root / 'tsconfig.json').write_text(json.dumps({'compilerOptions': {'baseUrl': name}}),
                                            encoding='utf-8')
    monkeypatch.setattr(javascript, '_TSCONFIG_FIND_CACHE', {})
    for root in _two_projects(tmp_path, write):
        monkeypatch.chdir(root)
        assert javascript._find_tsconfig(javascript.Path('src'), None) == root / 'tsconfig.json'


def test_workspace_packages_follow_the_cwd(tmp_path, monkeypatch):
    def write(root, name):
        (root / 'package.json').write_text(json.dumps({'workspaces': ['packages/*']}),
                                           encoding='utf-8')
        member = root / 'packages' / 'member'
        member.mkdir(parents=True)
        (member / 'package.json').write_text(json.dumps({'name': f'@{name}/member'}),
                                             encoding='utf-8')
    monkeypatch.setattr(javascript, '_WORKSPACE_PACKAGES_CACHE', {})
    for root in _two_projects(tmp_path, write):
        monkeypatch.chdir(root)
        packages = javascript._find_workspace_packages(javascript.Path('.'))
        assert packages == {f'@{root.name}/member': root / 'packages' / 'member'}


def test_a_schema_file_is_cached_by_file_not_by_name(tmp_path, monkeypatch):
    def write(root, name):
        (root / 's.yaml').write_text(f'name: {name}\nrequired_fields: [title]\n', encoding='utf-8')
    monkeypatch.setattr(SchemaLoader, '_schema_cache', {})
    for root in _two_projects(tmp_path, write):
        monkeypatch.chdir(root)
        assert SchemaLoader.load_schema('./s.yaml')['name'] == root.name
