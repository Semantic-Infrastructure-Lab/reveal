"""The registry's extension sets follow the registry (BACK-2120).

``get_code_extensions`` and ``get_markdown_extensions`` were ``lru_cache``d with no key, so the
first call froze the answer. Plugin discovery is lazy (the first ``get_analyzer`` call runs it),
and ``ast://`` asks for the code extensions before it analyses any file, so an analyzer a
plugin registered afterwards was missing from the set: ``reveal ast://.`` skipped a plugin's
files, in a fresh process too.
"""
import textwrap
from pathlib import Path
from typing import Optional

import pytest

from reveal import api
from reveal.base import FileAnalyzer
from reveal.registry import (
    _ANALYZER_REGISTRY,
    _reset_plugin_discovery,
    discover_plugins,
    get_code_extensions,
    get_markdown_extensions,
    register,
)


@pytest.fixture
def registry_restored():
    """Run with a clean discovery state and put the registry back afterwards."""
    saved = _ANALYZER_REGISTRY.copy()
    _reset_plugin_discovery()
    yield
    _reset_plugin_discovery()
    _ANALYZER_REGISTRY.clear()
    _ANALYZER_REGISTRY.update(saved)


def _plugin(project: Path, extension: str, plugin_dir: Optional[Path] = None) -> None:
    plugin_dir = plugin_dir or project / '.reveal' / 'analyzers'
    plugin_dir.mkdir(parents=True)
    (plugin_dir / 'foox_analyzer.py').write_text(textwrap.dedent(f"""\
        from reveal.base import FileAnalyzer
        from reveal.registry import register

        @register('{extension}', name='Foox', icon='')
        class FooxAnalyzer(FileAnalyzer):
            def get_structure(self, **kwargs):
                return {{'functions': [{{'line': 1, 'line_end': 2, 'name': 'hello',
                                        'signature': '()', 'complexity': 1, 'depth': 0}}]}}
    """), encoding='utf-8')


def test_code_extensions_include_an_analyzer_registered_after_the_first_call(registry_restored):
    before = get_code_extensions()
    assert '.fooa' not in before

    @register('.fooa', name='Fooa')
    class FooaAnalyzer(FileAnalyzer):
        pass

    assert '.fooa' in get_code_extensions()
    assert before <= get_code_extensions()  # negative control: nothing already known is lost


def test_markdown_extensions_include_an_analyzer_registered_after_the_first_call(registry_restored):
    before = get_markdown_extensions()
    assert '.mdfoo' not in before

    @register('.mdfoo', name='Markdown', category='doc')
    class MdFooAnalyzer(FileAnalyzer):
        pass

    assert '.mdfoo' in get_markdown_extensions()
    assert before <= get_markdown_extensions()


def test_code_extensions_follow_a_direct_registry_edit(registry_restored):
    """Tests and tools edit ``_ANALYZER_REGISTRY`` without the decorator."""
    assert '.foob' not in get_code_extensions()
    _ANALYZER_REGISTRY['.foob'] = type('FoobAnalyzer', (FileAnalyzer,), {})
    assert '.foob' in get_code_extensions()
    del _ANALYZER_REGISTRY['.foob']
    assert '.foob' not in get_code_extensions()


def test_discovered_plugin_extension_is_a_code_extension(registry_restored, tmp_path):
    before = get_code_extensions()
    _reset_plugin_discovery()  # discovery runs once per process; the first call above may have used it
    _plugin(tmp_path, '.fooc')
    discover_plugins(cwd=tmp_path)
    assert '.fooc' in get_code_extensions()
    assert get_code_extensions() - {'.fooc'} == before


def test_first_extension_answer_discovers_plugins(registry_restored, tmp_path, monkeypatch):
    """Discovery is lazy; the answer for a process that has not discovered yet includes it."""
    _plugin(tmp_path, '.fooe')
    get_code_extensions()  # primed in a directory without plugins
    monkeypatch.chdir(tmp_path)
    _reset_plugin_discovery()  # what a fresh process looks like, with the cache still warm
    assert '.fooe' in get_code_extensions()


def test_first_markdown_answer_discovers_plugins(registry_restored, tmp_path, monkeypatch):
    plugin_dir = tmp_path / '.reveal' / 'analyzers'
    plugin_dir.mkdir(parents=True)
    (plugin_dir / 'mdx_analyzer.py').write_text(textwrap.dedent("""\
        from reveal.base import FileAnalyzer
        from reveal.registry import register

        @register('.mdxx', name='Markdown', category='doc')
        class MdxAnalyzer(FileAnalyzer):
            pass
    """), encoding='utf-8')
    get_markdown_extensions()
    monkeypatch.chdir(tmp_path)
    _reset_plugin_discovery()
    assert '.mdxx' in get_markdown_extensions()


def test_ast_directory_query_reaches_a_plugin_file(registry_restored, tmp_path, monkeypatch):
    """The user-visible failure: the walk's extension set was read before discovery ran.

    The plugin lives in the user-global plugin directory and the queried directory holds
    only the plugin's file, so nothing but the extension filter can trigger discovery.
    """
    home = tmp_path / 'home'
    _plugin(home, '.food', plugin_dir=home / '.reveal' / 'plugins')
    project = tmp_path / 'project'
    project.mkdir()
    (project / 'a.food').write_text('hello\n', encoding='utf-8')
    monkeypatch.setenv('HOME', str(home))
    monkeypatch.setenv('USERPROFILE', str(home))
    get_code_extensions()  # a warm cache, as in a process that has already answered once
    monkeypatch.chdir(project)
    _reset_plugin_discovery()
    files = {row['file'] for row in api.query('ast://.')['results']}
    assert 'a.food' in files


def test_ast_directory_query_still_reaches_a_builtin_file(registry_restored, tmp_path, monkeypatch):
    """Negative control: the same query on a directory with a built-in language file."""
    (tmp_path / 'b.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    get_code_extensions()
    _reset_plugin_discovery()
    assert {row['file'] for row in api.query('ast://.')['results']} == {'b.py'}
