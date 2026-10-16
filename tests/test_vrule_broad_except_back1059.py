"""BACK-1059: V-rule handlers catch the errors their body can raise, not Exception.

A V-rule that could not inspect something used to log at debug (or warn) and report
no finding, so a broken rule read as clean. Two shapes are pinned here:

* narrowed: the expected failure (OSError / UnicodeDecodeError / SyntaxError ...)
  is recorded as an ``unavailable`` rule outcome, and an UNEXPECTED exception (a bug
  in the rule or a callee) escapes the rule, where ``RuleRegistry.check_file``
  records it as a failed rule instead of a clean one;
* boundary: a loop over arbitrary adapters keeps going, but each skipped subject is
  recorded as ``unavailable`` rather than only logged.

Every unexpected-exception test is the red test; the expected-exception tests are the
negative controls (same outcome before and after, except where the old code only
logged).
"""
import json
import logging
from pathlib import Path

import pytest

from reveal.rules.validation import (
    V001, V002, V003, V005, V008, V009, V014, V015, V016, V018, V021, V023, V027, V028,
    V030, V031, V032, utils as vutils,
)
from reveal.rules.validation.V001 import V001 as V001Rule
from reveal.rules.validation.V002 import V002 as V002Rule
from reveal.rules.validation.V003 import AnalyzerContext, V003 as V003Rule
from reveal.rules.validation.V005 import V005 as V005Rule
from reveal.rules.validation.V008 import V008 as V008Rule
from reveal.rules.validation.V009 import V009 as V009Rule
from reveal.rules.validation.V014 import V014 as V014Rule
from reveal.rules.validation.V015 import V015 as V015Rule
from reveal.rules.validation.V016 import V016 as V016Rule
from reveal.rules.validation.V018 import V018 as V018Rule
from reveal.rules.validation.V019 import V019 as V019Rule
from reveal.rules.validation.V021 import V021 as V021Rule
from reveal.rules.validation.V023 import V023 as V023Rule
from reveal.rules.validation.V027 import V027 as V027Rule
from reveal.rules.validation.V028 import V028 as V028Rule
from reveal.rules.validation.V030 import V030 as V030Rule
from reveal.rules.validation.V031 import V031 as V031Rule
from reveal.rules.validation.V032 import V032 as V032Rule

BOOM = RuntimeError('boom: a bug, not an expected failure')


def _statuses(rule):
    return [o['status'] for o in rule.outcomes]


def _raise_on_read(monkeypatch, name, exc):
    """Path.read_text raises *exc* for files called *name*; other files read normally."""
    real = Path.read_text

    def fake(self, *args, **kwargs):
        if self.name == name:
            raise exc
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', fake)


def _raise_on_iterdir(monkeypatch, exc):
    def fake(self, *args, **kwargs):
        raise exc

    monkeypatch.setattr(Path, 'iterdir', fake)


def _root(tmp_path, monkeypatch, *modules):
    """A fake reveal package dir (tmp/reveal) that find_reveal_root returns in *modules*."""
    root = tmp_path / 'reveal'
    for sub in ('analyzers', 'rules', 'adapters', 'docs'):
        (root / sub).mkdir(parents=True)
    for module in modules:
        monkeypatch.setattr(module, 'find_reveal_root', lambda *a, **k: root)
    return root


# --- V001 / V005: STATIC_HELP read -------------------------------------------------

HELP_PY = "STATIC_HELP = {\n    'markdown': 'MARKDOWN_GUIDE.md',\n}\n"


@pytest.mark.parametrize('module, rule_cls', [(V001, V001Rule), (V005, V005Rule)])
def test_static_help_unreadable_is_unavailable_not_a_finding(
        module, rule_cls, tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch, module)
    (root / 'adapters' / 'help.py').write_text(HELP_PY, encoding='utf-8')
    (root / 'analyzers' / 'markdown.py').write_text('x = 1\n', encoding='utf-8')
    _raise_on_read(monkeypatch, 'help.py', PermissionError('denied'))
    rule = rule_cls()
    assert rule.check('reveal://', None, '') == []
    assert 'unavailable' in _statuses(rule)


@pytest.mark.parametrize('module, rule_cls', [(V001, V001Rule), (V005, V005Rule)])
def test_static_help_bug_escapes_the_rule(module, rule_cls, tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch, module)
    (root / 'adapters' / 'help.py').write_text(HELP_PY, encoding='utf-8')
    _raise_on_read(monkeypatch, 'help.py', BOOM)
    with pytest.raises(RuntimeError, match='boom'):
        rule_cls().check('reveal://', None, '')


@pytest.mark.parametrize('rule_cls', [V001Rule, V005Rule])
def test_static_help_readable_control(rule_cls, tmp_path):
    root = tmp_path / 'reveal'
    (root / 'adapters').mkdir(parents=True)
    (root / 'adapters' / 'help.py').write_text(HELP_PY, encoding='utf-8')
    rule = rule_cls()
    assert rule._get_static_help(root) == {'markdown': 'MARKDOWN_GUIDE.md'}
    assert rule.outcomes == []


# --- V002 / V021: one analyzer file read -------------------------------------------

def test_v002_unreadable_analyzer_is_unavailable(tmp_path):
    bad = tmp_path / 'foo.py'
    bad.write_bytes(b'\xff\xfe\x00bad utf-8 \xff')
    rule = V002Rule()
    assert rule._check_analyzer_registration(bad, tmp_path) is None
    assert _statuses(rule) == ['unavailable']


def test_v002_bug_escapes_the_rule(tmp_path, monkeypatch):
    target = tmp_path / 'foo.py'
    target.write_text('x = 1\n', encoding='utf-8')
    _raise_on_read(monkeypatch, 'foo.py', BOOM)
    with pytest.raises(RuntimeError, match='boom'):
        V002Rule()._check_analyzer_registration(target, tmp_path)


def test_v021_unreadable_analyzer_is_unavailable(tmp_path):
    adir = tmp_path / 'analyzers'
    adir.mkdir()
    bad = adir / 'foo.py'
    bad.write_bytes(b'\xff\xfe\x00bad utf-8 \xff')
    rule = V021Rule()
    assert rule._check_analyzer_file(bad, adir) is None
    assert _statuses(rule) == ['unavailable']


def test_v021_bug_escapes_the_rule(tmp_path, monkeypatch):
    adir = tmp_path / 'analyzers'
    adir.mkdir()
    target = adir / 'foo.py'
    target.write_text('import re\n', encoding='utf-8')
    _raise_on_read(monkeypatch, 'foo.py', BOOM)
    with pytest.raises(RuntimeError, match='boom'):
        V021Rule()._check_analyzer_file(target, adir)


# --- V003 -------------------------------------------------------------------------

def _ctx(tmp_path, name='foo'):
    path = tmp_path / f'{name}.py'
    return AnalyzerContext(analyzer_name=name, analyzer_path=path, reveal_root=tmp_path)


def test_v003_unreadable_analyzer_is_unavailable(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.analyzer_path.write_bytes(b'\xff\xfe\x00bad utf-8 \xff')
    rule = V003Rule()
    assert rule._check_analyzer_features(ctx, False) == []
    assert _statuses(rule) == ['unavailable']


def test_v003_bug_after_the_read_escapes_the_rule(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    ctx.analyzer_path.write_text('class FooAnalyzer(FileAnalyzer):\n    pass\n', encoding='utf-8')
    rule = V003Rule()

    def broken(content):
        raise BOOM

    monkeypatch.setattr(rule, '_check_hierarchy_support', broken)
    with pytest.raises(RuntimeError, match='boom'):
        rule._check_analyzer_features(ctx, True)


def test_v003_readable_control_still_flags_missing_structure(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.analyzer_path.write_text('x = 1\n', encoding='utf-8')
    rule = V003Rule()
    found = rule._check_analyzer_features(ctx, False)
    assert [d.rule_code for d in found] == ['V003']
    assert rule.outcomes == []


# --- V008 -------------------------------------------------------------------------

def test_v008_syntax_error_is_unavailable(tmp_path):
    bad = tmp_path / 'foo.py'
    bad.write_text('def (:\n', encoding='utf-8')
    rule = V008Rule()
    assert rule._check_analyzer_file(bad) == []
    assert _statuses(rule) == ['unavailable']


def test_v008_unreadable_is_unavailable(tmp_path):
    bad = tmp_path / 'foo.py'
    bad.write_bytes(b'\xff\xfe\x00bad utf-8 \xff')
    rule = V008Rule()
    assert rule._check_analyzer_file(bad) == []
    assert _statuses(rule) == ['unavailable']


def test_v008_bug_in_the_signature_walk_escapes_the_rule(tmp_path, monkeypatch):
    target = tmp_path / 'foo.py'
    target.write_text('x = 1\n', encoding='utf-8')
    rule = V008Rule()

    def broken(tree, path):
        raise BOOM

    monkeypatch.setattr(rule, '_find_get_structure_violations', broken)
    with pytest.raises(RuntimeError, match='boom'):
        rule._check_analyzer_file(target)


def test_v008_bug_in_the_parser_escapes_the_rule(tmp_path, monkeypatch):
    target = tmp_path / 'foo.py'
    target.write_text('x = 1\n', encoding='utf-8')

    def broken(*args, **kwargs):
        raise BOOM

    monkeypatch.setattr(V008, 'parse_python', broken)
    with pytest.raises(RuntimeError, match='boom'):
        V008Rule()._check_analyzer_file(target)


# --- V009 -------------------------------------------------------------------------

def test_v009_value_error_is_unavailable(tmp_path, monkeypatch):
    def invalid(*args, **kwargs):
        raise ValueError('embedded null byte')

    monkeypatch.setattr(V009, 'Path', invalid)
    rule = V009Rule()
    assert rule._resolve_link(tmp_path / 'a.md', 'b.md', tmp_path) is None
    assert _statuses(rule) == ['unavailable']


def test_v009_bug_escapes_the_rule(tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise BOOM

    monkeypatch.setattr(V009, 'Path', broken)
    with pytest.raises(RuntimeError, match='boom'):
        V009Rule()._resolve_link(tmp_path / 'a.md', 'b.md', tmp_path)


# --- V014 -------------------------------------------------------------------------

def _agent_help(tmp_path):
    path = tmp_path / 'AGENT_HELP.md'
    path.write_text('---\nhelp_token_estimate: ~9\n---\nbody ~1K tokens\n', encoding='utf-8')
    return path


def test_v014_estimate_unreadable_is_unavailable(tmp_path):
    path = tmp_path / 'AGENT_HELP.md'
    path.write_bytes(b'\xff\xfe\x00bad utf-8 \xff')
    rule = V014Rule()
    assert rule._estimate_tokens(path) is None
    assert _statuses(rule) == ['unavailable']


def test_v014_estimate_bug_escapes_the_rule(tmp_path, monkeypatch):
    path = _agent_help(tmp_path)
    _raise_on_read(monkeypatch, 'AGENT_HELP.md', BOOM)
    with pytest.raises(RuntimeError, match='boom'):
        V014Rule()._estimate_tokens(path)


def test_v014_frontmatter_bug_escapes_the_rule(tmp_path, monkeypatch):
    from reveal.adapters.markdown import files

    def broken(path):
        raise BOOM

    monkeypatch.setattr(files, 'extract_frontmatter', broken)
    with pytest.raises(RuntimeError, match='boom'):
        V014Rule()._check_frontmatter(_agent_help(tmp_path), 1000, 900.0, 1100.0)


def test_v014_frontmatter_claim_control(tmp_path):
    found = V014Rule()._check_frontmatter(_agent_help(tmp_path), 1000, 900.0, 1100.0)
    assert [d.rule_code for d in found] == ['V014']


@pytest.mark.parametrize('method', ['_check_body_line', '_check_help_py_literals'])
def test_v014_line_scans_unreadable_are_unavailable(method, tmp_path):
    path = tmp_path / 'AGENT_HELP.md'
    path.write_bytes(b'\xff\xfe\x00bad utf-8 \xff')
    rule = V014Rule()
    assert getattr(rule, method)(path, 1000, 900.0, 1100.0) == []
    assert _statuses(rule) == ['unavailable']


@pytest.mark.parametrize('method', ['_check_body_line', '_check_help_py_literals'])
def test_v014_line_scans_bug_escapes_the_rule(method, tmp_path, monkeypatch):
    path = _agent_help(tmp_path)
    _raise_on_read(monkeypatch, 'AGENT_HELP.md', BOOM)
    with pytest.raises(RuntimeError, match='boom'):
        getattr(V014Rule(), method)(path, 1000, 900.0, 1100.0)


# --- V015 -------------------------------------------------------------------------

def test_v015_rule_listing_oserror_is_unavailable(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch, V015)
    (root / 'rules' / 'bugs').mkdir()
    _raise_on_iterdir(monkeypatch, PermissionError('denied'))
    rule = V015Rule()
    assert rule._count_registered_rules() is None
    assert _statuses(rule) == ['unavailable']


def test_v015_rule_listing_bug_escapes_the_rule(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch, V015)
    _raise_on_iterdir(monkeypatch, BOOM)
    with pytest.raises(RuntimeError, match='boom'):
        V015Rule()._count_registered_rules()


def test_v015_counts_rule_files_control(tmp_path, monkeypatch):
    root = _root(tmp_path, monkeypatch, V015)
    cat = root / 'rules' / 'bugs'
    cat.mkdir()
    (cat / 'B001.py').write_text('', encoding='utf-8')
    (cat / '__init__.py').write_text('', encoding='utf-8')
    assert V015Rule()._count_registered_rules() == 1


def test_v015_readme_unreadable_is_unavailable(tmp_path):
    readme = tmp_path / 'README.md'
    readme.write_bytes(b'\xff\xfe\x00bad utf-8 \xff')
    rule = V015Rule()
    assert rule._extract_rules_count_from_readme(readme) == []
    assert _statuses(rule) == ['unavailable']


def test_v015_readme_bug_escapes_the_rule(tmp_path, monkeypatch):
    readme = tmp_path / 'README.md'
    readme.write_text('50 built-in rules\n', encoding='utf-8')
    _raise_on_read(monkeypatch, 'README.md', BOOM)
    with pytest.raises(RuntimeError, match='boom'):
        V015Rule()._extract_rules_count_from_readme(readme)


# --- V016 (boundary kept, skipped subject now an outcome) -------------------------

class _BrokenAnalyzer:
    def __init__(self, path):
        self.path = path

    def get_structure(self):
        raise BOOM


def test_v016_adapter_file_it_could_not_analyze_is_unavailable(tmp_path, monkeypatch):
    import reveal.registry as registry

    root = _root(tmp_path, monkeypatch, V016)
    monkeypatch.setattr(V016, 'is_dev_checkout', lambda r: True)
    (root / 'adapters' / 'foo.py').write_text('x = 1\n', encoding='utf-8')
    monkeypatch.setattr(registry, 'get_analyzer', lambda *a, **k: _BrokenAnalyzer)
    rule = V016Rule()
    assert rule._check_reveal_adapters() == []
    assert _statuses(rule) == ['unavailable']
    assert 'foo.py' in rule.outcomes[0]['subject']
    assert 'RuntimeError' in rule.outcomes[0]['reason']


def test_v016_file_with_no_analyzer_is_not_an_outcome_control(tmp_path, monkeypatch):
    import reveal.registry as registry

    root = _root(tmp_path, monkeypatch, V016)
    monkeypatch.setattr(V016, 'is_dev_checkout', lambda r: True)
    (root / 'adapters' / 'foo.py').write_text('x = 1\n', encoding='utf-8')
    monkeypatch.setattr(registry, 'get_analyzer', lambda *a, **k: None)
    rule = V016Rule()
    assert rule._check_reveal_adapters() == []
    assert rule.outcomes == []


# --- V018 -------------------------------------------------------------------------

def test_v018_missing_registry_symbol_is_unavailable(tmp_path, monkeypatch):
    from reveal.adapters import base

    _root(tmp_path, monkeypatch, V018)
    monkeypatch.delattr(base, 'list_renderer_schemes')
    rule = V018Rule()
    assert rule.check('reveal://', None, '') == []
    assert _statuses(rule) == ['unavailable']


def test_v018_registry_bug_escapes_the_rule(tmp_path, monkeypatch):
    from reveal.adapters import base

    _root(tmp_path, monkeypatch, V018)

    def broken():
        raise BOOM

    monkeypatch.setattr(base, 'list_supported_schemes', broken)
    with pytest.raises(RuntimeError, match='boom'):
        V018Rule().check('reveal://', None, '')


# --- V023 -------------------------------------------------------------------------

class _FakeAdapter:
    def get_structure(self):
        return {}


def test_v023_bug_in_the_pattern_check_escapes_the_rule(monkeypatch):
    monkeypatch.setattr(V023, 'get_adapter_class', lambda scheme: _FakeAdapter)
    rule = V023Rule()

    def broken(*args, **kwargs):
        raise BOOM

    monkeypatch.setattr(rule, '_check_output_code_patterns', broken)
    with pytest.raises(RuntimeError, match='boom'):
        rule._check_adapter_output('reveal/adapters/foo.py', 'def get_structure(self): pass')


def test_v023_unregistered_scheme_is_a_clean_skip_control(monkeypatch):
    monkeypatch.setattr(V023, 'get_adapter_class', lambda scheme: None)
    rule = V023Rule()
    assert rule._check_adapter_output('reveal/adapters/foo.py', 'x') == []
    assert rule.outcomes == []


# --- V027 (boundary kept, skipped scheme now an outcome) --------------------------

class _SchemaRaises:
    @staticmethod
    def get_schema():
        raise BOOM


def test_v027_adapter_whose_schema_cannot_be_read_is_unavailable(tmp_path, monkeypatch):
    from reveal.adapters import base

    root = _root(tmp_path, monkeypatch, V027)
    (root / 'docs' / 'adapters').mkdir()
    guide = tmp_path / 'ZZZ_GUIDE.md'
    guide.write_text('# zzz\n', encoding='utf-8')
    monkeypatch.setattr(base, '_ADAPTER_REGISTRY', {'zzz': _SchemaRaises})
    rule = V027Rule()
    monkeypatch.setattr(rule, '_guess_guide_file', lambda scheme, d: guide)
    assert rule.check('reveal://', None, '') == []
    assert _statuses(rule) == ['unavailable']
    assert rule.outcomes[0]['subject'] == 'zzz://'
    assert 'RuntimeError' in rule.outcomes[0]['reason']


# --- V028 -------------------------------------------------------------------------

def _help_data(tmp_path, monkeypatch, text):
    root = _root(tmp_path, monkeypatch, V028)
    data = root / 'adapters' / 'help_data'
    data.mkdir()
    (data / 'zzz.yaml').write_text(text, encoding='utf-8')
    return root


def test_v028_malformed_yaml_is_unavailable(tmp_path, monkeypatch):
    _help_data(tmp_path, monkeypatch, 'key: [unclosed\n')
    rule = V028Rule()
    assert rule.check('reveal://', None, '') == []
    assert _statuses(rule) == ['unavailable']
    assert 'zzz.yaml' in rule.outcomes[0]['subject']


def test_v028_unreadable_yaml_is_unavailable(tmp_path, monkeypatch):
    _help_data(tmp_path, monkeypatch, 'a: 1\n')
    _raise_on_read(monkeypatch, 'zzz.yaml', PermissionError('denied'))
    rule = V028Rule()
    assert rule.check('reveal://', None, '') == []
    assert _statuses(rule) == ['unavailable']


def test_v028_bug_escapes_the_rule(tmp_path, monkeypatch):
    import yaml

    _help_data(tmp_path, monkeypatch, 'a: 1\n')

    def broken(*args, **kwargs):
        raise BOOM

    monkeypatch.setattr(yaml, 'safe_load', broken)
    with pytest.raises(RuntimeError, match='boom'):
        V028Rule().check('reveal://', None, '')


def test_v028_clean_yaml_control(tmp_path, monkeypatch):
    _help_data(tmp_path, monkeypatch, 'a: 1\n')
    rule = V028Rule()
    assert rule.check('reveal://', None, '') == []
    assert 'unavailable' not in _statuses(rule)


# --- V030 / V031: one documentation read -------------------------------------------

def test_v030_unreadable_readme_is_unavailable(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch, V030)
    (tmp_path / 'README.md').write_text('x\n', encoding='utf-8')
    _raise_on_read(monkeypatch, 'README.md', PermissionError('denied'))
    rule = V030Rule()
    assert rule.check('reveal://', None, '') == []
    assert _statuses(rule) == ['unavailable']


def test_v030_readme_bug_escapes_the_rule(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch, V030)
    (tmp_path / 'README.md').write_text('x\n', encoding='utf-8')
    _raise_on_read(monkeypatch, 'README.md', BOOM)
    with pytest.raises(RuntimeError, match='boom'):
        V030Rule().check('reveal://', None, '')


def test_v031_unreadable_doc_is_unavailable(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch, V031)
    (tmp_path / 'VALIDATION.md').write_text('x\n', encoding='utf-8')
    _raise_on_read(monkeypatch, 'VALIDATION.md', PermissionError('denied'))
    rule = V031Rule()
    assert rule.check('reveal://', None, '') == []
    assert _statuses(rule) == ['unavailable']


def test_v031_doc_bug_escapes_the_rule(tmp_path, monkeypatch):
    _root(tmp_path, monkeypatch, V031)
    (tmp_path / 'VALIDATION.md').write_text('x\n', encoding='utf-8')
    _raise_on_read(monkeypatch, 'VALIDATION.md', BOOM)
    with pytest.raises(RuntimeError, match='boom'):
        V031Rule().check('reveal://', None, '')


# --- V032: PyPI lookup -------------------------------------------------------------

class _Response:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _urlopen(monkeypatch, result):
    import urllib.request

    def fake(*args, **kwargs):
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(urllib.request, 'urlopen', fake)


def _url_error():
    import urllib.error
    return urllib.error.URLError('offline')


@pytest.mark.parametrize('result', [
    _url_error(),
    TimeoutError('timed out'),
    _Response(b'not json'),
    _Response(b'{"info": {}}'),
    _Response(b'[]'),
], ids=['urlerror', 'timeout', 'bad-json', 'missing-key', 'wrong-shape'])
def test_v032_expected_lookup_failures_are_unavailable(result, monkeypatch):
    _urlopen(monkeypatch, result)
    rule = V032Rule()
    assert rule._latest_pypi_version() is None
    assert _statuses(rule) == ['unavailable']


def test_v032_bug_escapes_the_rule(monkeypatch):
    _urlopen(monkeypatch, BOOM)
    with pytest.raises(RuntimeError, match='boom'):
        V032Rule()._latest_pypi_version()


def test_v032_published_version_control(monkeypatch):
    _urlopen(monkeypatch, _Response(json.dumps({'info': {'version': '1.2.3'}}).encode()))
    rule = V032Rule()
    assert rule._latest_pypi_version() == '1.2.3'
    assert rule.outcomes == []


# --- validation/utils.py: scan_doc_for_counts --------------------------------------

def test_scan_doc_for_counts_unreadable_doc_is_not_a_clean_empty_result(tmp_path):
    doc = tmp_path / 'README.md'
    doc.write_bytes(b'\xff\xfe\x00bad utf-8 \xff')
    with pytest.raises(UnicodeDecodeError):
        vutils.scan_doc_for_counts(doc, [r'(\d+) rules'])


def test_scan_doc_for_counts_readable_control(tmp_path):
    doc = tmp_path / 'README.md'
    doc.write_text('we ship 7 rules\n', encoding='utf-8')
    assert vutils.scan_doc_for_counts(doc, [r'(\d+) rules']) == [(1, 7)]


def test_unreadable_claim_doc_fails_the_rule_in_the_registry(tmp_path, monkeypatch):
    """End to end: V012 reads claim docs through the helper; the registry reports it failed."""
    from reveal.rules import RuleRegistry
    from reveal.rules.validation import V012

    (tmp_path / 'README.md').write_bytes(b'\xff\xfe\x00bad utf-8 \xff')
    root = tmp_path / 'reveal'
    root.mkdir()
    monkeypatch.setattr(V012, 'find_reveal_root', lambda *a, **k: root)
    monkeypatch.setattr(V012.V012, '_count_supported_languages', lambda self: 10)
    monkeypatch.setattr(V012, 'iter_current_claim_docs',
                        lambda project_root: [('README.md', tmp_path / 'README.md')])
    errors = []
    RuleRegistry.check_file('reveal://', None, '', select=['V012'], errors=errors)
    assert [e['rule'] for e in errors] == ['V012']
    assert 'UnicodeDecodeError' in errors[0]['error']


# --- schemas/frontmatter: SchemaLoader.load_schema ---------------------------------

def _loader():
    from reveal.schemas.frontmatter import SchemaLoader
    SchemaLoader._schema_cache.clear()
    return SchemaLoader


def test_schema_loader_expected_failures_return_none(tmp_path):
    loader = _loader()
    scalar = tmp_path / 'scalar.yaml'
    scalar.write_text('5\n', encoding='utf-8')          # valid YAML, not a mapping
    bad_date = tmp_path / 'date.yaml'
    bad_date.write_text('name: 2024-13-45\nrequired_fields: []\n', encoding='utf-8')
    unparsable = tmp_path / 'broken.yaml'
    unparsable.write_text('name: [unclosed\n', encoding='utf-8')
    not_utf8 = tmp_path / 'binary.yaml'
    not_utf8.write_bytes(b'\xff\xfe\x00bad utf-8 \xff')
    for path in (scalar, bad_date, unparsable, not_utf8, tmp_path):
        assert loader.load_schema(str(path)) is None, path


def test_schema_loader_valid_schema_control(tmp_path):
    loader = _loader()
    ok = tmp_path / 'ok.yaml'
    ok.write_text('name: demo\nrequired_fields: [title]\n', encoding='utf-8')
    assert loader.load_schema(str(ok))['name'] == 'demo'


def test_schema_loader_bug_escapes(tmp_path, monkeypatch):
    import yaml
    loader = _loader()
    ok = tmp_path / 'ok.yaml'
    ok.write_text('name: demo\nrequired_fields: [title]\n', encoding='utf-8')

    def broken(*args, **kwargs):
        raise BOOM

    monkeypatch.setattr(yaml, 'safe_load', broken)
    with pytest.raises(RuntimeError, match='boom'):
        loader.load_schema(str(ok))


# --- testability/patches.py: TypeScript scan ---------------------------------------

def test_ts_scan_without_a_grammar_warns_and_returns_nothing(tmp_path, monkeypatch, caplog):
    from reveal.core.treesitter_parse import GrammarUnavailable
    from reveal.testability import patches

    src = tmp_path / 'a.test.ts'
    src.write_text("jest.mock('./x');\n", encoding='utf-8')

    def unavailable(*args, **kwargs):
        raise GrammarUnavailable('typescript', ImportError('no pack'))

    monkeypatch.setattr(patches, 'get_tree', unavailable)
    with caplog.at_level(logging.WARNING, logger=patches.logger.name):
        assert patches._scan_file_ts(src) == []
    assert any('tree-sitter parse failed' in r.getMessage() for r in caplog.records)


def test_ts_scan_bug_escapes(tmp_path, monkeypatch):
    from reveal.testability import patches

    src = tmp_path / 'a.test.ts'
    src.write_text("jest.mock('./x');\n", encoding='utf-8')

    def broken(*args, **kwargs):
        raise BOOM

    monkeypatch.setattr(patches, 'get_tree', broken)
    with pytest.raises(RuntimeError, match='boom'):
        patches._scan_file_ts(src)


# --- V019: resource-init probe (boundary kept, environmental skip now an outcome) --

class _NeedsRealResource:
    def __init__(self, resource=None):
        if resource is not None:
            raise FileNotFoundError(f'no such resource: {resource}')


class _ReadsMissingAttribute:
    def __init__(self, resource=None):
        if resource is not None:
            self.missing.attribute


def test_v019_resource_init_needing_a_real_resource_is_not_applicable(tmp_path):
    rule = V019Rule()
    adapter_file = tmp_path / 'zzz.py'
    adapter_file.write_text('class Z:\n    def __init__(self):\n        pass\n', encoding='utf-8')
    assert rule._test_resource_init('zzz', _NeedsRealResource, adapter_file) is None
    assert _statuses(rule) == ['skipped']
    assert rule.outcomes[0]['subject'] == 'zzz: resource init'
    assert 'FileNotFoundError' in rule.outcomes[0]['reason']


def test_v019_attribute_error_is_still_a_finding_control(tmp_path):
    rule = V019Rule()
    adapter_file = tmp_path / 'zzz.py'
    adapter_file.write_text('class Z:\n    def __init__(self):\n        pass\n', encoding='utf-8')
    found = rule._test_resource_init('zzz', _ReadsMissingAttribute, adapter_file)
    assert found is not None and 'AttributeError' in found.message
    assert rule.outcomes == []
