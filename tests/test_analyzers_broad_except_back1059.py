"""BACK-1059: file-format analyzers catch the errors their input file can produce and let a
bug in reveal propagate; a bad layer configuration fails naming its file.

An unexpected failure is injected as ``_InjectedBug`` (an Exception subclass that is
neither a RuntimeError nor a ValueError, so no narrowed handler here lists it). Each group
also holds negative controls: the expected error still takes the old path.
"""

import csv
import json
import logging
import lzma
import struct
import zipfile
from pathlib import Path

import pytest
import yaml
from bs4 import FeatureNotFound
from bs4.builder import ParserRejectedMarkup

from conftest import _run_reveal_direct
from reveal.analyzers import html as html_mod
from reveal.analyzers import markdown as markdown_mod
from reveal.analyzers.csv_analyzer import CsvAnalyzer
from reveal.analyzers.html import HTMLAnalyzer
from reveal.analyzers.imports import javascript as js_imports
from reveal.analyzers.imports import python as py_imports
from reveal.analyzers.imports.base import LanguageExtractor
from reveal.analyzers.imports.go import GoExtractor
from reveal.analyzers.imports.layers import LayerConfig, load_layer_config
from reveal.analyzers.jupyter_analyzer import JupyterAnalyzer
from reveal.analyzers.markdown import MarkdownAnalyzer, RelatedTracker
from reveal.analyzers.office import DocxAnalyzer
from reveal.analyzers.office import base as office_base
from reveal.analyzers.xml_analyzer import XmlAnalyzer

pytestmark = pytest.mark.component


class _InjectedBug(Exception):
    """A failure no handler here expects: stands in for a bug in reveal."""


def _raise_bug(*_a, **_k):
    raise _InjectedBug('injected')


def _write(path: Path, text: str, encoding: str = 'utf-8') -> Path:
    path.write_bytes(text.encode(encoding))
    return path


# ------------------------------------------------------------------------- csv

def test_csv_sniffer_bug_propagates(tmp_path, monkeypatch):
    path = _write(tmp_path / 'a.csv', 'a,b\n1,2\n')
    monkeypatch.setattr(csv.Sniffer, 'sniff', _raise_bug)
    with pytest.raises(_InjectedBug):
        CsvAnalyzer(str(path)).get_structure()


@pytest.mark.parametrize('name, expected', [('one.csv', ','), ('one.tsv', '\t')])
def test_csv_sniffer_csv_error_still_falls_back_to_extension(tmp_path, name, expected):
    # a single column gives the sniffer nothing to choose between: csv.Error
    path = _write(tmp_path / name, 'alpha\nbeta\n')
    assert CsvAnalyzer(str(path))._get_delimiter(path.read_text(encoding='utf-8')) == expected


def test_csv_file_of_quoted_values_does_not_get_the_quote_as_delimiter(tmp_path):
    # csv.Sniffer returns '"' here, which csv.reader rejects on 3.14 (ValueError)
    path = _write(tmp_path / 'q.csv', '"x"\n"y"\n')
    analyzer = CsvAnalyzer(str(path))
    assert analyzer._get_delimiter(analyzer.content) == ','
    assert 'error' not in analyzer.get_structure()


def test_csv_parse_bug_propagates(tmp_path, monkeypatch):
    path = _write(tmp_path / 'a.csv', 'a,b\n1,2\n')
    monkeypatch.setattr(CsvAnalyzer, '_calculate_column_stats', _raise_bug)
    with pytest.raises(_InjectedBug):
        CsvAnalyzer(str(path)).get_structure()


def test_csv_field_over_the_size_limit_is_still_an_error_result(tmp_path):
    big = 'x' * (csv.field_size_limit() + 10)
    path = _write(tmp_path / 'big.csv', f'a,b\n{big},2\n')
    result = CsvAnalyzer(str(path)).get_structure()
    assert result.get('error'), result


# ------------------------------------------------------------------------- xml

def test_xml_analysis_bug_propagates(tmp_path, monkeypatch):
    path = _write(tmp_path / 'a.xml', '<a><b/></a>')
    monkeypatch.setattr(XmlAnalyzer, '_count_elements', _raise_bug)
    with pytest.raises(_InjectedBug):
        XmlAnalyzer(str(path)).get_structure()


def test_xml_nested_deeper_than_the_recursion_limit_is_still_an_error_result(tmp_path):
    depth = 3000   # ET parses it; _count_elements/_max_depth recurse once per level
    path = _write(tmp_path / 'deep.xml', '<a>' * depth + '</a>' * depth)
    result = XmlAnalyzer(str(path)).get_structure()
    assert result.get('error'), result


def test_xml_malformed_is_still_a_parse_error_result(tmp_path):
    path = _write(tmp_path / 'bad.xml', '<a><b></a>')
    result = XmlAnalyzer(str(path)).get_structure()
    assert 'XML parse error' in result['error']


# ----------------------------------------------------------------------- jupyter

def test_notebook_decode_bug_propagates(tmp_path, monkeypatch):
    path = _write(tmp_path / 'n.ipynb', '{"cells": []}')
    monkeypatch.setattr(json, 'loads', _raise_bug)
    with pytest.raises(_InjectedBug):
        JupyterAnalyzer(str(path))


def test_notebook_invalid_json_is_still_a_parse_error(tmp_path):
    path = _write(tmp_path / 'n.ipynb', '{"cells": [')
    analyzer = JupyterAnalyzer(str(path))
    assert analyzer.parse_error
    assert analyzer.get_structure().get('error')


def test_notebook_nested_past_the_recursion_limit_is_still_a_parse_error(tmp_path):
    path = _write(tmp_path / 'n.ipynb', '[' * 100000)
    assert JupyterAnalyzer(str(path)).parse_error


@pytest.mark.parametrize('text', ['[]', '"x"', '3'])
def test_notebook_that_is_not_a_json_object_is_a_parse_error_naming_the_cause(tmp_path, text):
    path = _write(tmp_path / 'n.ipynb', text)
    analyzer = JupyterAnalyzer(str(path))
    assert analyzer.parse_error and 'expected an object' in analyzer.parse_error
    assert analyzer.get_structure().get('error')


# -------------------------------------------------------------------------- html

def test_html_parser_bug_propagates(tmp_path, monkeypatch):
    path = _write(tmp_path / 'a.html', '<p>x</p>')
    monkeypatch.setattr(html_mod, 'BeautifulSoup', _raise_bug)
    with pytest.raises(_InjectedBug):
        HTMLAnalyzer(str(path))


@pytest.mark.parametrize('rejection', [
    pytest.param(lambda: FeatureNotFound('no lxml'), id='lxml-not-installed'),
    pytest.param(lambda: ParserRejectedMarkup('lxml refused it'), id='lxml-refused-markup'),
])
def test_html_lxml_rejection_still_falls_back_to_html_parser(tmp_path, monkeypatch, rejection):
    path = _write(tmp_path / 'a.html', '<p>x</p>')
    real = html_mod.BeautifulSoup
    parsers = []

    def soup(content, parser):
        parsers.append(parser)
        if parser == 'lxml':
            raise rejection()
        return real(content, parser)

    monkeypatch.setattr(html_mod, 'BeautifulSoup', soup)
    analyzer = HTMLAnalyzer(str(path))
    assert parsers == ['lxml', 'html.parser'] and analyzer.soup.find('p')


# ---------------------------------------------------------------------- markdown

def _frontmatter_analyzer(tmp_path, body='a: 1'):
    return MarkdownAnalyzer(str(_write(tmp_path / 'd.md', f'---\n{body}\n---\n# Title\n')))


def test_frontmatter_yaml_bug_propagates(tmp_path, monkeypatch):
    analyzer = _frontmatter_analyzer(tmp_path)
    monkeypatch.setattr(markdown_mod.yaml, 'safe_load', _raise_bug)
    with pytest.raises(_InjectedBug):
        analyzer._extract_frontmatter()


@pytest.mark.parametrize('body', [
    pytest.param('a: [', id='yaml-syntax-error'),
    pytest.param('date: 2001-02-30', id='impossible-date'),
    pytest.param('n: !!int 1e999', id='impossible-int'),
    pytest.param('x: ' + '[' * 100000, id='nested-past-recursion-limit'),
])
def test_frontmatter_that_yaml_rejects_is_still_none(tmp_path, body):
    assert _frontmatter_analyzer(tmp_path, body)._extract_frontmatter() is None


def test_frontmatter_valid_still_parses(tmp_path):
    assert _frontmatter_analyzer(tmp_path)._extract_frontmatter()['data'] == {'a': 1}


def _related(tmp_path, target: Path):
    source = MarkdownAnalyzer(str(_write(tmp_path / 'src.md', '# Source\n')))
    return source._process_related_path(target.name, tmp_path, RelatedTracker(depth=1))


def test_related_file_analysis_bug_propagates(tmp_path, monkeypatch):
    target = _write(tmp_path / 'other.md', '# Other\n')
    monkeypatch.setattr(MarkdownAnalyzer, '_extract_headings', _raise_bug)
    with pytest.raises(_InjectedBug):
        _related(tmp_path, target)


def test_related_file_that_cannot_be_read_is_still_an_error_entry(tmp_path):
    unreadable = tmp_path / 'dir.md'
    unreadable.mkdir()     # exists, has a markdown suffix, cannot be opened as a file
    entry = _related(tmp_path, unreadable)
    assert entry['exists'] and entry['error'] and entry['headings'] == []


def test_related_file_still_lists_its_headings(tmp_path):
    entry = _related(tmp_path, _write(tmp_path / 'other.md', '# Other\n'))
    assert entry['headings'] == ['Other'] and 'error' not in entry


# ------------------------------------------------------------------------ office

def _docx(path: Path, parts=None) -> Path:
    parts = parts or {
        'word/document.xml': '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>',
        'docProps/core.xml': '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"/>',
    }
    with zipfile.ZipFile(path, 'w') as zf:
        for name, text in parts.items():
            zf.writestr(name, text)
    return path


def _docx_analyzer(tmp_path) -> DocxAnalyzer:
    return DocxAnalyzer(str(_docx(tmp_path / 'd.docx')))


def _quiet_close(analyzer):
    analyzer.archive = None    # so the real __del__ at collection has nothing to raise from


@pytest.mark.parametrize('reader', ['_read_xml', '_read_part'], ids=['read_xml', 'read_part'])
def test_office_part_read_bug_propagates(tmp_path, reader):
    analyzer = _docx_analyzer(tmp_path)
    analyzer._safe_read = _raise_bug
    with pytest.raises(_InjectedBug):
        getattr(analyzer, reader)('word/document.xml')


@pytest.mark.parametrize('failure', [
    zipfile.BadZipFile('Bad CRC-32'),
    KeyError('word/document.xml'),
    ValueError('Part too large'),
    NotImplementedError('That compression method is not supported'),
    RuntimeError("File 'word/document.xml' is encrypted, password required"),
    EOFError('Compressed file ended before the end-of-stream marker was reached'),
    OSError('read error'),
    lzma.LZMAError('Corrupt input data'),  # zipfile lets it through; not an OSError
], ids=lambda f: type(f).__name__)
@pytest.mark.parametrize('reader', ['_read_xml', '_read_part'], ids=['read_xml', 'read_part'])
def test_office_part_the_archive_cannot_deliver_is_still_none(tmp_path, reader, failure):
    analyzer = _docx_analyzer(tmp_path)

    def damaged(_part):
        raise failure
    analyzer._safe_read = damaged
    assert getattr(analyzer, reader)('word/document.xml') is None


@pytest.mark.parametrize('content', [
    pytest.param(b'<a', id='truncated-xml'),
    pytest.param(b'<?xml version="1.0" encoding="nope"?><a/>', id='unknown-encoding'),
])
def test_office_malformed_xml_part_is_still_none(tmp_path, content):
    analyzer = DocxAnalyzer(str(_docx(tmp_path / 'd.docx', {
        'word/document.xml': '<w:document xmlns:w="u"/>', 'bad.xml': content})))
    assert analyzer.parse_error is None
    assert analyzer._read_xml('bad.xml') is None


def test_office_open_bug_propagates(tmp_path, monkeypatch):
    path = _docx(tmp_path / 'd.docx')
    monkeypatch.setattr(office_base.zipfile, 'ZipFile', _raise_bug)
    with pytest.raises(_InjectedBug):
        DocxAnalyzer(str(path))


def test_office_not_a_zip_is_still_a_parse_error(tmp_path):
    path = _write(tmp_path / 'junk.docx', 'not a zip file')
    assert 'Invalid ZIP archive' in DocxAnalyzer(str(path)).parse_error


def test_office_missing_file_is_still_a_parse_error(tmp_path):
    assert 'Error opening document' in DocxAnalyzer(str(tmp_path / 'absent.docx')).parse_error


def test_office_unknown_xml_encoding_in_the_content_part_is_still_a_parse_error(tmp_path):
    # ET.fromstring(bytes) raises LookupError, not ParseError, for an unknown encoding
    path = _docx(tmp_path / 'd.docx', {'word/document.xml': '<?xml version="1.0" encoding="nope"?><a/>'})
    assert 'Error opening document' in DocxAnalyzer(str(path)).parse_error


def test_office_unsupported_compression_method_is_still_a_parse_error(tmp_path):
    path = _docx(tmp_path / 'd.docx')
    data = bytearray(path.read_bytes())
    # method 99 in the local header and the central directory entry of the first member
    struct.pack_into('<H', data, data.index(b'PK\x03\x04') + 8, 99)
    struct.pack_into('<H', data, data.index(b'PK\x01\x02') + 10, 99)
    path.write_bytes(bytes(data))
    assert 'Error opening document' in DocxAnalyzer(str(path)).parse_error


def test_office_media_listing_bug_propagates(tmp_path):
    analyzer = DocxAnalyzer(str(_docx(tmp_path / 'm.docx', {
        'word/document.xml': '<w:document xmlns:w="u"/>', 'word/media/i.png': 'x'})))

    class _Archive:
        getinfo = staticmethod(_raise_bug)
    analyzer.archive = _Archive()
    with pytest.raises(_InjectedBug):
        analyzer._get_embedded_media()
    _quiet_close(analyzer)


def test_office_media_entry_missing_from_the_archive_is_skipped_with_a_warning(tmp_path, caplog):
    analyzer = DocxAnalyzer(str(_docx(tmp_path / 'm.docx', {
        'word/document.xml': '<w:document xmlns:w="u"/>', 'word/media/i.png': 'x', 'word/media/j.png': 'y'})))
    real = analyzer.archive

    class _Archive:
        @staticmethod
        def getinfo(name):
            if name.endswith('i.png'):
                raise KeyError(name)
            return real.getinfo(name)
    analyzer.archive = _Archive()
    with caplog.at_level(logging.WARNING):
        media = analyzer._get_embedded_media()
    assert [m['name'] for m in media] == ['j.png']
    assert 'i.png' in caplog.text
    analyzer.archive = real


def test_office_close_bug_is_not_swallowed_in_del(tmp_path):
    analyzer = _docx_analyzer(tmp_path)

    class _Archive:
        close = staticmethod(_raise_bug)
    analyzer.archive = _Archive()
    with pytest.raises(_InjectedBug):
        analyzer.__del__()
    _quiet_close(analyzer)


def test_office_close_os_error_is_swallowed_in_del(tmp_path):
    analyzer = _docx_analyzer(tmp_path)

    def broken_close():
        raise OSError('close failed')

    class _Archive:
        close = staticmethod(broken_close)
    analyzer.archive = _Archive()
    analyzer.__del__()
    _quiet_close(analyzer)


# ------------------------------------------------------------------------ imports

def test_go_mod_read_bug_propagates(tmp_path, monkeypatch):
    (tmp_path / 'go.mod').write_text('module example.com/m\n', encoding='utf-8')
    real = Path.read_text

    def read_text(self, *a, **k):
        if self.name == 'go.mod':
            raise _InjectedBug('injected')
        return real(self, *a, **k)
    monkeypatch.setattr(Path, 'read_text', read_text)
    with pytest.raises(_InjectedBug):
        GoExtractor()._get_module_name(tmp_path)


def test_go_mod_that_cannot_be_read_still_gives_no_module_name(tmp_path):
    (tmp_path / 'go.mod').mkdir()
    assert GoExtractor()._get_module_name(tmp_path) is None


def test_go_mod_that_is_not_utf8_still_gives_no_module_name(tmp_path):
    (tmp_path / 'go.mod').write_bytes(b'module \xff\xfe\n')
    assert GoExtractor()._get_module_name(tmp_path) is None


def test_go_mod_still_gives_its_module_name(tmp_path):
    (tmp_path / 'go.mod').write_text('module example.com/m\n', encoding='utf-8')
    assert GoExtractor()._get_module_name(tmp_path) == 'example.com/m'


def test_pnpm_workspace_yaml_bug_propagates(tmp_path, monkeypatch):
    (tmp_path / 'pnpm-workspace.yaml').write_text('packages:\n  - "a/*"\n', encoding='utf-8')
    monkeypatch.setattr(yaml, 'safe_load', _raise_bug)
    with pytest.raises(_InjectedBug):
        js_imports._load_workspace_package_globs(tmp_path)


@pytest.mark.parametrize('body', ['packages: [', 'packages: 2001-02-30'], ids=['syntax-error', 'impossible-date'])
def test_pnpm_workspace_yaml_that_yaml_rejects_is_still_no_globs_and_warns(tmp_path, caplog, body):
    (tmp_path / 'pnpm-workspace.yaml').write_text(body + '\n', encoding='utf-8')
    with caplog.at_level(logging.WARNING, logger=js_imports.logger.name):
        assert js_imports._load_workspace_package_globs(tmp_path) == []
    assert 'pnpm-workspace.yaml' in caplog.text


def test_pnpm_workspace_yaml_still_gives_its_globs(tmp_path):
    (tmp_path / 'pnpm-workspace.yaml').write_text('packages:\n  - "a/*"\n', encoding='utf-8')
    assert js_imports._load_workspace_package_globs(tmp_path) == ['a/*']


def test_python_noqa_read_bug_propagates(tmp_path, monkeypatch):
    path = _write(tmp_path / 'm.py', 'import os\n')
    monkeypatch.setattr(py_imports, 'open', _raise_bug, raising=False)
    with pytest.raises(_InjectedBug):
        py_imports.PythonExtractor()._extract_imports_uncached(path)


def test_python_file_that_is_not_utf8_still_yields_its_imports(tmp_path):
    path = tmp_path / 'm.py'
    path.write_bytes('# caf\xe9\nimport os\n'.encode('latin-1'))
    imports = py_imports.PythonExtractor()._extract_imports_uncached(path)
    assert [i.module_name for i in imports] == ['os']


def test_import_analyzer_construction_failure_is_disclosed_as_parse_failed(tmp_path, monkeypatch):
    # the boundary-ok handler in _get_tree_analyzer: one file's failure must be visible
    # through parse_failed and the diagnostics every graph consumer reads
    path = _write(tmp_path / 'm.py', 'import os\n')
    extractor = py_imports.PythonExtractor()

    class _Broken:
        def __init__(self, _path):
            raise _InjectedBug('grammar failed to load')
    monkeypatch.setattr(LanguageExtractor.__module__ + '.get_analyzer', lambda _p: _Broken)
    assert extractor._get_tree_analyzer(path) is None
    assert extractor.parse_failed
    assert extractor.analysis.diagnostics['parse'] == {'status': 'unavailable', 'reason': 'grammar failed to load'}


# ------------------------------------------------------------------------- layers

def test_layer_config_error_is_a_value_error():
    from reveal.analyzers.imports.layers import LayerConfigError
    assert issubclass(LayerConfigError, ValueError)


_LAYER = {'name': 'api', 'paths': ['api/'], 'deny_imports': ['db/']}


def test_layer_definition_that_is_not_a_mapping_is_not_skipped():
    with pytest.raises(ValueError, match=r'layers\[1\]'):
        LayerConfig.from_dict({'architecture': {'layers': [_LAYER, 'not-a-dict']}})


def test_layer_definition_that_is_not_a_mapping_fails_naming_its_source():
    with pytest.raises(ValueError, match=r'/p/\.reveal\.yaml.*layers\[0\]'):
        LayerConfig.from_dict({'architecture': {'layers': [7]}}, source='/p/.reveal.yaml')


@pytest.mark.parametrize('config', [
    pytest.param(['a', 'list'], id='top-level-list'),
    pytest.param({'architecture': 5}, id='architecture-scalar'),
    pytest.param({'architecture': {'layers': 'api'}}, id='layers-string'),
])
def test_layer_config_of_the_wrong_shape_fails_naming_its_source(config):
    with pytest.raises(ValueError, match=r'/p/\.reveal\.yaml'):
        LayerConfig.from_dict(config, source='/p/.reveal.yaml')


def test_valid_layers_still_load():
    config = LayerConfig.from_dict({'architecture': {'layers': [_LAYER]}})
    assert [layer.name for layer in config.layers] == ['api']
    assert LayerConfig.from_dict({}).layers == []


def _reveal_yaml(root: Path, text: str) -> Path:
    path = root / '.reveal.yaml'
    path.write_text(text, encoding='utf-8')
    return path


def test_load_layer_config_with_a_bad_layer_fails_naming_the_config_file(tmp_path):
    config_file = _reveal_yaml(tmp_path, 'root: true\narchitecture:\n  layers:\n    - not-a-dict\n')
    with pytest.raises(ValueError) as excinfo:
        load_layer_config(tmp_path)
    assert str(config_file) in str(excinfo.value)


def test_load_layer_config_fallback_with_a_yaml_syntax_error_fails_naming_the_file(tmp_path, monkeypatch):
    config_file = _reveal_yaml(tmp_path, 'architecture: [')
    monkeypatch.setattr('reveal.config.RevealConfig.get', _raise_os_error)
    with pytest.raises(ValueError) as excinfo:
        load_layer_config(tmp_path)
    assert str(config_file) in str(excinfo.value)


def test_load_layer_config_fallback_with_a_bad_layer_fails_naming_the_file(tmp_path, monkeypatch):
    config_file = _reveal_yaml(tmp_path, 'architecture:\n  layers:\n    - 7\n')
    monkeypatch.setattr('reveal.config.RevealConfig.get', _raise_os_error)
    with pytest.raises(ValueError, match=r'layers\[0\]') as excinfo:
        load_layer_config(tmp_path)
    assert str(config_file) in str(excinfo.value)


def _raise_os_error(*_a, **_k):
    raise OSError('config unavailable')


def test_load_layer_config_primary_failure_is_warned_and_falls_back(tmp_path, monkeypatch, caplog):
    _reveal_yaml(tmp_path, 'architecture:\n  layers:\n    - name: api\n      paths: [api/]\n')
    monkeypatch.setattr('reveal.config.RevealConfig.get', _raise_os_error)
    with caplog.at_level(logging.WARNING):
        config = load_layer_config(tmp_path)
    assert [layer.name for layer in config.layers] == ['api']
    assert 'config unavailable' in caplog.text


def test_load_layer_config_valid_file_still_loads(tmp_path):
    _reveal_yaml(tmp_path, 'root: true\narchitecture:\n  layers:\n    - name: api\n      paths: [api/]\n')
    assert [layer.name for layer in load_layer_config(tmp_path).layers] == ['api']


def test_imports_violations_with_a_bad_layer_exits_1_and_names_the_config_file(tmp_path):
    config_file = _reveal_yaml(tmp_path, 'root: true\narchitecture:\n  layers:\n    - not-a-dict\n')
    (tmp_path / 'a.py').write_text('import os\n', encoding='utf-8')
    result = _run_reveal_direct(f'imports://{tmp_path}?violations')
    assert result.returncode == 1, (result.stdout, result.stderr)
    assert str(config_file) in result.stderr
