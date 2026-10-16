"""BACK-1059 (rules outside validation/): handlers catch what their body can raise.

A rule that could not inspect something used to log (or say nothing) and return no
finding, so a broken rule read as clean. The shapes pinned here:

* narrowed: the expected failure is recorded as an ``unavailable`` rule outcome and an
  UNEXPECTED exception (a bug in the rule or a callee) escapes the rule, where
  ``RuleRegistry.check_file`` records it as a failed rule instead of a clean one;
* boundary: a per-file body over arbitrary user source keeps catching broadly, but the
  failure is now an ``unavailable`` outcome with the file as subject, not only a log line;
* shared-index preloads (scan_caches): a failed preload is a scan disclosure, so the
  run is incomplete (exit 3) instead of silently letting workers rebuild without the cap
  disclosures only the parent can carry.

Every unexpected-exception / missing-outcome test is the red test; the expected-exception
and healthy-input tests are the negative controls (same outcome before and after).
"""
import http.client
import logging
import sys
import urllib.request
from pathlib import Path

import pytest

BOOM = RuntimeError('boom: a bug, not an expected failure')


def _boom(*args, **kwargs):
    raise BOOM


def _statuses(rule):
    return [o['status'] for o in rule.outcomes]


def _unavailable(rule):
    return [o for o in rule.outcomes if o['status'] == 'unavailable']


def _raise_on_read(monkeypatch, name, exc):
    """Path.read_text raises *exc* for files called *name*; other files read normally."""
    real = Path.read_text

    def fake(self, *args, **kwargs):
        if self.name == name:
            raise exc
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', fake)


# --- rules/base.py get_config -----------------------------------------------------

def test_get_config_failure_warns_and_names_the_error(monkeypatch, caplog):
    from reveal.config import RevealConfig
    from reveal.rules.maintainability.M501 import M501
    monkeypatch.setattr(RevealConfig, 'get', classmethod(
        lambda cls, *a, **k: (_ for _ in ()).throw(RuntimeError('config exploded'))))
    rule = M501()
    with caplog.at_level(logging.WARNING, logger='reveal.rules.base'):
        config = rule.get_config()
    assert config.get_rule_config('M501', 'x', 7) == 7        # defaults still apply
    messages = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    assert any('config exploded' in m and 'M501' in m for m in messages), messages


def test_get_config_healthy_is_silent(caplog):
    from reveal.rules.maintainability.M501 import M501
    with caplog.at_level(logging.WARNING, logger='reveal.rules.base'):
        M501().get_config()
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


# --- rules/base_mixins.py ---------------------------------------------------------

def test_cached_ast_parse_bug_escapes(monkeypatch):
    from reveal.rules import base_mixins
    monkeypatch.setattr(base_mixins, 'parse_python', _boom)
    with pytest.raises(RuntimeError, match='boom'):
        base_mixins._cached_ast_parse('x = 1  # bug-escapes\n', 'bug_escapes.py')


@pytest.mark.parametrize('exc', [ValueError('source code string cannot contain null bytes'),
                                 RecursionError('too deep')])
def test_cached_ast_parse_expected_failures_still_none_with_warning(monkeypatch, caplog, exc):
    from reveal.rules import base_mixins

    def raiser(*a, **k):
        raise exc

    monkeypatch.setattr(base_mixins, 'parse_python', raiser)
    with caplog.at_level(logging.WARNING, logger='reveal.rules.base_mixins'):
        tree = base_mixins._cached_ast_parse(f'x = 1  # {type(exc).__name__}\n', 'expected.py')
    assert tree is None
    assert any('expected.py' in r.getMessage() for r in caplog.records)


# --- rules/__init__.py: external rule module loader --------------------------------

@pytest.mark.parametrize('body', ['raise RuntimeError("load boom")\n', 'raise SystemExit(3)\n'])
def test_failed_external_module_is_unregistered_and_error_propagates(tmp_path, body):
    from reveal.rules import RuleRegistry
    plugin = tmp_path / 'X900.py'
    plugin.write_text(body, encoding='utf-8')
    name = 'reveal._external_rules.test.X900'
    with pytest.raises((RuntimeError, SystemExit)):
        RuleRegistry._load_module_from_path(plugin, name)
    assert name not in sys.modules


def test_loaded_external_module_stays_registered(tmp_path):
    from reveal.rules import RuleRegistry
    plugin = tmp_path / 'X901.py'
    plugin.write_text('VALUE = 5\n', encoding='utf-8')
    name = 'reveal._external_rules.test.X901'
    try:
        module = RuleRegistry._load_module_from_path(plugin, name)
        assert module.VALUE == 5 and sys.modules[name] is module
    finally:
        sys.modules.pop(name, None)


# --- I001 / I008 / I007: per-file extractor bodies ---------------------------------

class _Boom:
    parse_failed = False

    def extract_imports(self, path):
        raise BOOM

    def extract_symbols(self, path):
        raise BOOM


def test_i001_extractor_failure_is_unavailable_with_file_subject(tmp_path, monkeypatch):
    from reveal.rules.imports import I001 as module
    src = tmp_path / 'mod.py'
    src.write_text('import os\n', encoding='utf-8')
    monkeypatch.setattr(module, 'get_extractor', lambda p: _Boom())
    rule = module.I001()
    assert rule.check(str(src), None, src.read_text(encoding='utf-8')) == []
    assert [o['subject'] for o in _unavailable(rule)] == [str(src)]
    assert 'boom' in _unavailable(rule)[0]['reason']


def test_i001_healthy_file_has_no_outcome(tmp_path):
    from reveal.rules.imports.I001 import I001
    src = tmp_path / 'mod.py'
    src.write_text('import os\n', encoding='utf-8')
    rule = I001()
    assert len(rule.check(str(src), None, src.read_text(encoding='utf-8'))) == 1   # unused os
    assert rule.outcomes == []


def test_i008_analysis_failure_is_unavailable(tmp_path, monkeypatch):
    from reveal.rules.imports.I008 import I008
    src = tmp_path / 'mod.py'
    src.write_text('import yaml\n', encoding='utf-8')
    monkeypatch.setattr(I008, '_check_python', _boom)
    rule = I008()
    assert rule.check(str(src), None, '') == []
    assert [o['subject'] for o in _unavailable(rule)] == [str(src)]


def test_i007_analysis_failure_is_unavailable(tmp_path, monkeypatch):
    from reveal.rules.imports import I007 as module
    manifest = tmp_path / 'pyproject.toml'
    manifest.write_text('[project]\nname = "p"\ndependencies = ["foo"]\n', encoding='utf-8')
    monkeypatch.setattr(module, 'python_declared_unused', _boom)
    rule = module.I007()
    assert rule.check(str(manifest), None, '') == []
    assert [o['subject'] for o in _unavailable(rule)] == [str(manifest.resolve())]


def _dep_project(tmp_path):
    (tmp_path / 'pyproject.toml').write_text(
        '[project]\nname = "p"\nversion = "1"\ndependencies = ["foo"]\n', encoding='utf-8')
    (tmp_path / 'a.py').write_text('import foo\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('x = 1\n', encoding='utf-8')
    return tmp_path / 'pyproject.toml'


def test_i007_skipped_source_file_is_disclosed(tmp_path, monkeypatch):
    from reveal.rules.imports import _dep_reconciliation as dep
    from reveal.rules.imports.I007 import I007
    manifest = _dep_project(tmp_path)
    dep._scan_project_imports.cache_clear()
    real = dep.get_extractor

    def flaky(fp):
        if Path(fp).name == 'a.py':
            return _Boom()
        return real(fp)

    monkeypatch.setattr(dep, 'get_extractor', flaky)
    rule = I007()
    detections = rule.check(str(manifest), None, '')
    dep._scan_project_imports.cache_clear()
    assert [d.context for d in detections] == ['declared dependency never imported: foo']
    unavailable = _unavailable(rule)
    assert len(unavailable) == 1 and 'a.py' in unavailable[0]['reason'], rule.outcomes


def test_i007_all_files_scanned_has_no_outcome(tmp_path):
    from reveal.rules.imports import _dep_reconciliation as dep
    from reveal.rules.imports.I007 import I007
    manifest = _dep_project(tmp_path)
    dep._scan_project_imports.cache_clear()
    rule = I007()
    assert rule.check(str(manifest), None, '') == []           # foo is imported by a.py
    dep._scan_project_imports.cache_clear()
    assert rule.outcomes == []


# --- I002 ---------------------------------------------------------------------------

def test_i002_check_failure_is_unavailable(tmp_path, monkeypatch):
    from reveal.rules.imports import I002 as module
    src = tmp_path / 'a.py'
    src.write_text('import b\n', encoding='utf-8')
    monkeypatch.setattr(module, '_find_project_root', lambda p: tmp_path)
    monkeypatch.setattr(module.I002, '_build_import_graph', _boom)
    rule = module.I002()
    assert rule.check(str(src), None, '') == []
    assert [o['subject'] for o in _unavailable(rule)] == [str(src)]


def test_i002_healthy_check_has_no_outcome(tmp_path, monkeypatch):
    from reveal.rules.imports import I002 as module
    (tmp_path / 'a.py').write_text('import b\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('x = 1\n', encoding='utf-8')
    monkeypatch.setattr(module, '_find_project_root', lambda p: tmp_path)
    rule = module.I002()
    assert rule.check(str(tmp_path / 'a.py'), None, '') == []
    assert rule.outcomes == []


def test_i002_unextractable_file_is_a_failed_file_not_an_exception(tmp_path, monkeypatch):
    """The failed flag is the channel get_scan_disclosures reports (tag-only site pin)."""
    from reveal.rules.imports import I002 as module
    src = tmp_path / 'a.py'
    src.write_text('import b\n', encoding='utf-8')
    monkeypatch.setattr(module, 'get_extractor', lambda p: _Boom())
    assert module._extract_imports_for_file(str(src)) == ([], True)


# --- I003 ---------------------------------------------------------------------------

LAYERS = (
    'architecture:\n'
    '  layers:\n'
    '    - name: low\n'
    '      paths: ["low/**"]\n'
    '      deny_imports: ["high"]\n'
)


def _layer_project(tmp_path, config=LAYERS):
    (tmp_path / '.reveal.yaml').write_text(config, encoding='utf-8')
    (tmp_path / 'low').mkdir()
    (tmp_path / 'high').mkdir()
    (tmp_path / 'high' / '__init__.py').write_text('', encoding='utf-8')
    src = tmp_path / 'low' / 'm.py'
    src.write_text('import high\n', encoding='utf-8')
    return src


@pytest.mark.parametrize('config', ['architecture: [1, 2]\n', 'architecture: {layers: 7}\n',
                                    'a: [unclosed\n', '- just\n- a list\n'])
def test_i003_unusable_layer_config_is_unavailable_naming_the_file(tmp_path, config):
    from reveal.rules.imports.I003 import I003
    src = _layer_project(tmp_path, config)
    rule = I003()
    assert rule.check(str(src), None, '') == []
    unavailable = _unavailable(rule)
    assert len(unavailable) == 1, rule.outcomes
    assert '.reveal.yaml' in unavailable[0]['reason']
    assert unavailable[0]['subject'] == str(src)


def test_i003_valid_config_still_detects_and_has_no_outcome(tmp_path):
    from reveal.rules.imports.I003 import I003
    src = _layer_project(tmp_path)
    rule = I003()
    assert len(rule.check(str(src), None, '')) == 1
    assert rule.outcomes == []


def test_i003_no_layer_config_is_silent(tmp_path):
    from reveal.rules.imports.I003 import I003
    (tmp_path / 'm.py').write_text('import os\n', encoding='utf-8')
    rule = I003()
    assert rule.check(str(tmp_path / 'm.py'), None, '') == []
    assert rule.outcomes == []


def test_i003_config_lookup_environment_failure_is_unavailable(tmp_path, monkeypatch):
    from reveal.rules.imports.I003 import I003
    src = _layer_project(tmp_path)
    monkeypatch.setattr(I003, '_load_config_and_find_root',
                        lambda self, p: (_ for _ in ()).throw(ImportError('no yaml')))
    rule = I003()
    assert rule.check(str(src), None, '') == []
    assert [o['subject'] for o in _unavailable(rule)] == [str(src)]


def test_i003_config_lookup_bug_escapes(tmp_path, monkeypatch):
    from reveal.rules.imports.I003 import I003
    src = _layer_project(tmp_path)
    monkeypatch.setattr(I003, '_load_config_and_find_root', _boom)
    with pytest.raises(RuntimeError, match='boom'):
        I003().check(str(src), None, '')


def test_i003_import_extraction_failure_is_unavailable(tmp_path, monkeypatch):
    from reveal.rules.imports import I003 as module
    src = _layer_project(tmp_path)
    monkeypatch.setattr(module, 'extract_python_imports', _boom)
    rule = module.I003()
    assert rule.check(str(src), None, '') == []
    assert [o['subject'] for o in _unavailable(rule)] == [str(src)]


def test_i003_per_import_failure_is_unavailable(tmp_path, monkeypatch):
    from reveal.rules.imports import I003 as module
    src = _layer_project(tmp_path)
    monkeypatch.setattr(module, 'resolve_python_import', _boom)
    rule = module.I003()
    assert rule.check(str(src), None, '') == []
    unavailable = _unavailable(rule)
    assert len(unavailable) == 1 and unavailable[0]['subject'] == f'{src}:1', rule.outcomes


# --- I005 ---------------------------------------------------------------------------

class _Stmt:
    is_type_checking = False
    source_line = 'import os'
    line_number = 1


class _FlakyExtractor:
    """Yields one statement, then fails mid-iteration."""

    def extract_imports(self, path):
        yield _Stmt()
        raise BOOM


def test_i005_extractor_failure_is_unavailable_and_fallback_is_not_double_counted(
        tmp_path, monkeypatch):
    from reveal.rules.imports import I005 as module
    src = tmp_path / 'f.py'
    src.write_text('import os\n', encoding='utf-8')
    monkeypatch.setattr(module, 'get_extractor', lambda p: _FlakyExtractor())
    rule = module.I005()
    structure = {'imports': [{'content': 'import os', 'line': 1}]}
    detections = rule.check(str(src), structure, 'import os\n')
    # one real import: statements seen before the failure must not be counted again
    # by the structure fallback (it made `import os` a duplicate of itself)
    assert detections == []
    assert [o['subject'] for o in _unavailable(rule)] == [str(src)]


# --- N007 ---------------------------------------------------------------------------

def _nginx(cert):
    return ('server {\n    listen 443 ssl;\n    ssl_stapling on;\n'
            f'    ssl_certificate {cert};\n}}\n')


def test_n007_unparsable_certificate_is_unavailable(tmp_path):
    from reveal.rules.infrastructure.N007 import N007
    cert = tmp_path / 'cert.pem'
    cert.write_text('this is not a certificate\n', encoding='utf-8')
    rule = N007()
    assert rule.check('nginx.conf', None, _nginx(cert)) == []
    unavailable = _unavailable(rule)
    assert len(unavailable) == 1 and str(cert) in unavailable[0]['reason'], rule.outcomes


def test_n007_certificate_parser_bug_escapes(tmp_path, monkeypatch):
    import ssl
    from reveal.rules.infrastructure.N007 import N007
    cert = tmp_path / 'cert.pem'
    cert.write_text('-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n', encoding='utf-8')
    monkeypatch.setattr(ssl, 'PEM_cert_to_DER_cert', _boom)
    with pytest.raises(RuntimeError, match='boom'):
        N007().check('nginx.conf', None, _nginx(cert))


def test_n007_certificate_on_another_host_is_still_skipped_silently(tmp_path):
    from reveal.rules.infrastructure.N007 import N007
    rule = N007()
    assert rule.check('nginx.conf', None, _nginx(tmp_path / 'absent.pem')) == []
    assert rule.outcomes == []


# --- L001 ---------------------------------------------------------------------------

def _anchor_link_project(tmp_path):
    (tmp_path / 'a.md').write_text('[x](b.md#sec)\n', encoding='utf-8')
    (tmp_path / 'b.md').write_text('# Other\n', encoding='utf-8')
    return {'links': [{'text': 'x', 'url': 'b.md#sec', 'line': 1}]}


def test_l001_unreadable_headings_is_unavailable_not_a_broken_link(tmp_path, monkeypatch):
    from reveal.rules.links.L001 import L001
    structure = _anchor_link_project(tmp_path)

    class Broken:
        def __init__(self, path):
            raise BOOM

    monkeypatch.setattr('reveal.registry.get_analyzer', lambda p: Broken)
    rule = L001()
    assert rule.check(str(tmp_path / 'a.md'), structure, '[x](b.md#sec)\n') == []
    assert [o['subject'] for o in _unavailable(rule)] == [str(tmp_path / 'b.md')]


def test_l001_readable_headings_still_report_a_missing_anchor(tmp_path):
    from reveal.rules.links.L001 import L001
    structure = _anchor_link_project(tmp_path)
    rule = L001()
    found = rule.check(str(tmp_path / 'a.md'), structure, '[x](b.md#sec)\n')
    assert len(found) == 1 and 'b.md#sec' in found[0].message
    assert rule.outcomes == []


# --- L002 ---------------------------------------------------------------------------

def test_l002_validation_bug_is_unavailable_not_a_broken_link(tmp_path, monkeypatch):
    from reveal.rules.links.L002 import L002
    monkeypatch.setattr(L002, '_is_broken_link', _boom)
    rule = L002()
    structure = {'links': [{'text': 't', 'url': 'https://example.com/x', 'line': 3}]}
    assert rule.check(str(tmp_path / 'a.md'), structure, '') == []
    unavailable = _unavailable(rule)
    assert len(unavailable) == 1 and unavailable[0]['subject'] == str(tmp_path / 'a.md')
    assert 'https://example.com/x' in unavailable[0]['reason']


def test_l002_a_real_broken_link_is_still_reported(tmp_path, monkeypatch):
    from reveal.rules.links.L002 import L002
    monkeypatch.setattr(L002, '_is_broken_link', lambda self, url: (True, 'http_error', 404))
    rule = L002()
    structure = {'links': [{'text': 't', 'url': 'https://example.com/x', 'line': 3}]}
    assert len(rule.check(str(tmp_path / 'a.md'), structure, '')) == 1
    assert rule.outcomes == []


def test_l002_get_request_bug_escapes(monkeypatch):
    from reveal.rules.links.L002 import L002
    monkeypatch.setattr(urllib.request, 'urlopen', _boom)
    with pytest.raises(RuntimeError, match='boom'):
        L002()._try_get_request('https://example.com')


@pytest.mark.parametrize('exc', [OSError('reset'), ValueError('bad url'),
                                 http.client.BadStatusLine('x')])
def test_l002_get_request_expected_failures_stay_validation_errors(monkeypatch, caplog, exc):
    from reveal.rules.links.L002 import L002

    def raiser(*a, **k):
        raise exc

    monkeypatch.setattr(urllib.request, 'urlopen', raiser)
    with caplog.at_level(logging.WARNING, logger='reveal.rules.links.L002'):
        result = L002()._try_get_request('https://example.com')
    assert result == (True, 'validation_error', None)
    assert any(r.levelno >= logging.WARNING for r in caplog.records)


def test_l002_head_request_protocol_error_is_a_validation_error(monkeypatch):
    from reveal.rules.links.L002 import L002

    def raiser(*a, **k):
        raise http.client.BadStatusLine('garbage')

    monkeypatch.setattr(urllib.request, 'urlopen', raiser)
    assert L002()._is_broken_link('https://example.com') == (True, 'validation_error', None)


# --- M101 ---------------------------------------------------------------------------

def _big_file(tmp_path):
    src = tmp_path / 'big.py'
    content = 'x = 1\n' * 600
    src.write_text(content, encoding='utf-8')
    return src, content


def test_m101_unstatable_file_is_still_measured_from_its_content(tmp_path, monkeypatch):
    from reveal.rules.maintainability.M101 import M101
    src, content = _big_file(tmp_path)
    real = Path.stat

    def fake(self, *a, **k):
        if self.name == 'big.py':
            raise PermissionError('denied')
        return real(self, *a, **k)

    monkeypatch.setattr(Path, 'stat', fake)
    found = M101().check(str(src), None, content)
    assert len(found) == 1 and '600' in found[0].message


def test_m101_stat_bug_escapes(tmp_path, monkeypatch):
    from reveal.rules.maintainability.M101 import M101
    src, content = _big_file(tmp_path)
    real = Path.stat

    def fake(self, *a, **k):
        if self.name == 'big.py':
            raise BOOM
        return real(self, *a, **k)

    monkeypatch.setattr(Path, 'stat', fake)
    with pytest.raises(RuntimeError, match='boom'):
        M101().check(str(src), None, content)


def test_m101_readable_file_control(tmp_path):
    from reveal.rules.maintainability.M101 import M101
    src, content = _big_file(tmp_path)
    assert len(M101().check(str(src), None, content)) == 1


# --- M103 ---------------------------------------------------------------------------

def _version_project(tmp_path, pyproject):
    (tmp_path / 'pyproject.toml').write_text(pyproject, encoding='utf-8')
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    init = pkg / '__init__.py'
    init.write_text('__version__ = "1.0.0"\n', encoding='utf-8')
    return init


def test_m103_malformed_pyproject_is_unavailable(tmp_path):
    from reveal.rules.maintainability.M103 import M103
    init = _version_project(tmp_path, '[project\nversion = \n')
    rule = M103()
    assert rule.check(str(init), None, init.read_text(encoding='utf-8')) == []
    assert [o['subject'] for o in _unavailable(rule)] == [str(tmp_path / 'pyproject.toml')]


def test_m103_unreadable_pyproject_is_unavailable(tmp_path, monkeypatch):
    from reveal.rules.maintainability.M103 import M103
    init = _version_project(tmp_path, '[project]\nversion = "2.0.0"\n')
    _raise_on_read(monkeypatch, 'pyproject.toml', PermissionError('denied'))
    rule = M103()
    assert rule.check(str(init), None, init.read_text(encoding='utf-8')) == []
    assert len(_unavailable(rule)) == 1


def test_m103_parser_bug_escapes(tmp_path, monkeypatch):
    import importlib
    from reveal.rules.maintainability.M103 import M103
    init = _version_project(tmp_path, '[project]\nversion = "2.0.0"\n')
    # the module's own tomllib alias: stdlib tomllib, or tomli on Python < 3.11
    monkeypatch.setattr(importlib.import_module('reveal.rules.maintainability.M103').tomllib,
                        'loads', _boom)
    with pytest.raises(RuntimeError, match='boom'):
        M103().check(str(init), None, init.read_text(encoding='utf-8'))


def test_m103_mismatch_still_detected_and_wrong_shape_is_not_an_error(tmp_path):
    from reveal.rules.maintainability.M103 import M103
    init = _version_project(tmp_path, '[project]\nversion = "2.0.0"\n')
    rule = M103()
    assert len(rule.check(str(init), None, init.read_text(encoding='utf-8'))) == 1
    assert rule.outcomes == []
    (tmp_path / 'pyproject.toml').write_text('project = 3\n', encoding='utf-8')
    shaped = M103()
    assert shaped.check(str(init), None, init.read_text(encoding='utf-8')) == []
    assert shaped.outcomes == []


# --- M105 ---------------------------------------------------------------------------

def _handlers_project(tmp_path):
    cli = tmp_path / 'reveal' / 'cli'
    cli.mkdir(parents=True)
    handlers = cli / 'handlers_test.py'
    content = 'def handle_test():\n    pass\n'
    handlers.write_text(content, encoding='utf-8')
    (tmp_path / 'reveal' / 'main.py').write_text('# empty main\n', encoding='utf-8')
    return handlers, content


def test_m105_unreadable_wiring_source_is_unavailable(tmp_path, monkeypatch):
    from reveal.rules.maintainability.M105 import M105
    handlers, content = _handlers_project(tmp_path)
    _raise_on_read(monkeypatch, 'main.py', PermissionError('denied'))
    rule = M105()
    assert rule.check(str(handlers), None, content) == []
    assert [o['subject'] for o in _unavailable(rule)] == [str(tmp_path / 'reveal' / 'main.py')]


def test_m105_wiring_read_bug_escapes(tmp_path, monkeypatch):
    from reveal.rules.maintainability.M105 import M105
    handlers, content = _handlers_project(tmp_path)
    _raise_on_read(monkeypatch, 'main.py', BOOM)
    with pytest.raises(RuntimeError, match='boom'):
        M105().check(str(handlers), None, content)


def test_m105_readable_main_still_reports_an_unwired_handler(tmp_path):
    from reveal.rules.maintainability.M105 import M105
    handlers, content = _handlers_project(tmp_path)
    rule = M105()
    assert len(rule.check(str(handlers), None, content)) == 1
    assert rule.outcomes == []


# --- M501 ---------------------------------------------------------------------------

@pytest.mark.parametrize('bad', [5, 'remove in v', ['ok', 3], {'a': 1}])
def test_m501_unusable_ignore_patterns_config_is_unavailable(monkeypatch, bad):
    from reveal.rules.maintainability.M501 import M501
    monkeypatch.setattr(M501, 'get_threshold', lambda self, key, default: bad)
    rule = M501()
    assert rule.check('a.py', None, '# TODO: x\n') == []
    unavailable = _unavailable(rule)
    assert len(unavailable) == 1 and unavailable[0]['subject'] == 'a.py'
    assert 'ignore_patterns' in unavailable[0]['reason']


def test_m501_valid_ignore_patterns_and_default_control(monkeypatch):
    from reveal.rules.maintainability.M501 import M501
    content = '# TODO: x\n# TODO: remove in v2\n'
    plain = M501()
    assert len(plain.check('a.py', None, content)) == 2
    assert plain.outcomes == []
    monkeypatch.setattr(M501, 'get_threshold', lambda self, key, default: ['remove in v'])
    filtered = M501()
    assert len(filtered.check('a.py', None, content)) == 1
    assert filtered.outcomes == []


# --- U502 ---------------------------------------------------------------------------

@pytest.fixture
def _u502_caches(monkeypatch):
    from reveal.rules.urls import U502 as module
    monkeypatch.setattr(module, '_pyproject_dir_cache', {})
    monkeypatch.setattr(module, '_canonical_url_cache', {})
    return module


def _url_project(tmp_path, pyproject):
    (tmp_path / 'pyproject.toml').write_text(pyproject, encoding='utf-8')
    src = tmp_path / 'a.py'
    content = '# https://github.com/other/thing\n'
    src.write_text(content, encoding='utf-8')
    return src, content


GOOD_PYPROJECT = '[project]\nname = "p"\n[project.urls]\nHomepage = "https://github.com/org/proj"\n'


def test_u502_malformed_pyproject_is_unavailable_and_not_cached(tmp_path, _u502_caches):
    src, content = _url_project(tmp_path, '[project\nurls = \n')
    rule = _u502_caches.U502()
    assert rule.check(str(src), None, content) == []
    assert [o['subject'] for o in _unavailable(rule)] == [str(tmp_path / 'pyproject.toml')]
    # the failure must not poison the cache: once the manifest is fixed the rule sees it
    (tmp_path / 'pyproject.toml').write_text(GOOD_PYPROJECT, encoding='utf-8')
    fixed = _u502_caches.U502()
    assert len(fixed.check(str(src), None, content)) == 1
    assert fixed.outcomes == []


def test_u502_parser_bug_escapes(tmp_path, monkeypatch, _u502_caches):
    src, content = _url_project(tmp_path, GOOD_PYPROJECT)
    monkeypatch.setattr(_u502_caches.tomllib, 'loads', _boom)
    with pytest.raises(RuntimeError, match='boom'):
        _u502_caches.U502().check(str(src), None, content)


def test_u502_good_and_wrong_shaped_pyproject_controls(tmp_path, _u502_caches):
    src, content = _url_project(tmp_path, GOOD_PYPROJECT)
    rule = _u502_caches.U502()
    assert len(rule.check(str(src), None, content)) == 1
    assert rule.outcomes == []
    (tmp_path / 'pyproject.toml').write_text('project = 3\n', encoding='utf-8')
    _u502_caches._canonical_url_cache.clear()
    shaped = _u502_caches.U502()
    assert shaped.check(str(src), None, content) == []
    assert shaped.outcomes == []


# --- scan_caches: a failed shared-index preload is a scan disclosure ---------------

def _preload_owner(code):
    """(object whose attribute the preload's builder is reached through, attribute)."""
    from reveal.rules.imports import I002
    from reveal.rules.duplicates import D005
    from reveal.rules.types import T006
    from reveal.rules.maintainability import M102
    return {'I002': (I002.I002, '_build_import_graph'), 'D005': (D005, '_build_index'),
            'T006': (T006, '_build_index'), 'M102': (M102.M102, '_collect_all_imports')}[code]


@pytest.mark.parametrize('code, preload_name', [
    ('I002', '_i002_preload'), ('D005', '_d005_preload'),
    ('T006', '_t006_preload'), ('M102', '_m102_preload')])
def test_failed_preload_is_a_scan_disclosure(tmp_path, monkeypatch, code, preload_name):
    from reveal.rules import scan_caches
    owner, attr = _preload_owner(code)
    src = tmp_path / 'mod.py'
    src.write_text('x = 1\n', encoding='utf-8')
    monkeypatch.setattr(scan_caches, '_project_roots', lambda d, f, find: [tmp_path])
    monkeypatch.setattr(owner, attr, _boom)
    result = getattr(scan_caches, preload_name)(tmp_path, None, None, [src])
    assert result == {}
    disclosures = scan_caches.get_scan_disclosures([src], None, None)
    assert any(m.startswith(f'{code}:') and 'preload' in m and 'boom' in m
               for m in disclosures), disclosures


def test_preload_failure_does_not_outlive_the_next_preload_or_request(tmp_path, monkeypatch):
    from reveal.rules import scan_caches
    from reveal.rules.types import T006
    from reveal.utils.request_cache import reset_request_caches
    src = tmp_path / 'mod.py'
    src.write_text('x = 1\n', encoding='utf-8')
    monkeypatch.setattr(scan_caches, '_project_roots', lambda d, f, find: [tmp_path])
    monkeypatch.setattr(T006, '_build_index', _boom)
    scan_caches._t006_preload(tmp_path, None, None, [src])
    assert any(m.startswith('T006:') for m in scan_caches.get_scan_disclosures([src], None, None))
    reset_request_caches()
    assert not any(m.startswith('T006:')
                   for m in scan_caches.get_scan_disclosures([src], None, None))
    scan_caches._t006_preload(tmp_path, None, None, [src])
    assert any(m.startswith('T006:') for m in scan_caches.get_scan_disclosures([src], None, None))
    monkeypatch.undo()
    scan_caches.preload_scan_caches([], tmp_path, ['E501'], None)     # nothing selected runs
    assert not any(m.startswith('T006:')
                   for m in scan_caches.get_scan_disclosures([src], None, None))


def test_failed_preload_of_an_unselected_rule_is_not_reported(tmp_path, monkeypatch):
    from reveal.rules import scan_caches
    from reveal.rules.types import T006
    src = tmp_path / 'mod.py'
    src.write_text('x = 1\n', encoding='utf-8')
    monkeypatch.setattr(scan_caches, '_project_roots', lambda d, f, find: [tmp_path])
    monkeypatch.setattr(T006, '_build_index', _boom)
    scan_caches._t006_preload(tmp_path, None, None, [src])
    assert not any(m.startswith('T006:')
                   for m in scan_caches.get_scan_disclosures([src], ['E501'], None))


def test_healthy_preload_has_no_disclosure(tmp_path, monkeypatch):
    from reveal.rules import scan_caches
    src = tmp_path / 'mod.py'
    src.write_text('x = 1\n', encoding='utf-8')
    monkeypatch.setattr(scan_caches, '_project_roots', lambda d, f, find: [tmp_path])
    scan_caches._t006_preload(tmp_path, None, None, [src])
    assert not any('preload' in m for m in scan_caches.get_scan_disclosures([src], None, None))
