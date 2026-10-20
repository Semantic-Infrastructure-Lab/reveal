"""BACK-2078: JavaScript, TypeScript and TSX imports carry their edge scope.

The JS/TS extractor records ``ImportStatement.scope`` from ``node_taxonomy.edge_scope`` (the
helper Python uses, BACK-2076) and keeps ``dynamic`` as BACK-2076 set it. Before, every
JS/TS edge had scope None ("unclassified"): counted as load-time under every ``&lazy``
value, so an ``import()`` inside a function closed a phantom cycle in ``?circular``.

The rule is positional, as for Python: an import inside a function declaration, arrow
function, function expression, generator, method or object method is ``local``. A class
body is module scope, so a class field initializer and a static block are ``module``,
although an instance field runs at construction; an arrow function in a field is ``local``.
A top-level ``import()`` or ``require()`` is ``module`` and dynamic. TS ``import type``
is an ``es6_import`` at module scope, an edge in every view, as before.

Each case imports its own target, so the target's fan-in under ``&lazy=only`` and
``&lazy=exclude`` (JSON ``entries``) says which side the edge landed on.
"""

import json

import pytest
import tree_sitter_language_pack as ts

from conftest import _run_reveal_direct
from reveal.analyzers.imports.javascript import extract_js_imports
from reveal.core.treesitter_compat import _zero_arg, ts_parse, tree_root
from reveal.utils.path_utils import to_posix

M, L = 'module', 'local'

# name -> (statement template with {m} for the module specifier and {n} for a unique
# suffix, scope, dynamic). Every template is valid JavaScript, TypeScript and TSX.
CASES = {
    'es_import': ("import {{ x as x_{n} }} from '{m}';", M, False),
    'es_side_effect': ("import '{m}';", M, False),
    'top_dynamic': ("import('{m}');", M, True),
    'top_require': ("const r_{n} = require('{m}');", M, True),
    'reexport': ("export {{ x as y_{n} }} from '{m}';", M, False),
    'reexport_star': ("export * as ns_{n} from '{m}';", M, False),
    'function_declaration': ("function f_{n}() {{ return import('{m}'); }}", L, True),
    'function_require': ("function g_{n}() {{ return require('{m}'); }}", L, True),
    'async_function': ("async function af_{n}() {{ await import('{m}'); }}", L, True),
    'arrow_function': ("const a_{n} = () => import('{m}');", L, True),
    'function_expression': ("const e_{n} = function () {{ return require('{m}'); }};", L, True),
    'generator_declaration': ("function* gd_{n}() {{ yield import('{m}'); }}", L, True),
    'generator_expression': ("const ge_{n} = function* () {{ yield require('{m}'); }};", L, True),
    'method': ("class M_{n} {{ m() {{ return import('{m}'); }} }}", L, True),
    'object_method': ("const o_{n} = {{ m() {{ return require('{m}'); }} }};", L, True),
    'class_field': ("class F_{n} {{ x = import('{m}'); }}", M, True),
    'static_field': ("class S_{n} {{ static x = require('{m}'); }}", M, True),
    'static_block': ("class B_{n} {{ static {{ import('{m}'); }} }}", M, True),
    'class_field_arrow': ("class H_{n} {{ h = () => import('{m}'); }}", L, True),
}
TS_CASES = {
    'import_type': ("import type {{ x as t_{n} }} from '{m}';", M, False),
}

LANGUAGES = {'javascript': '.js', 'typescript': '.ts', 'tsx': '.tsx'}


def _cases(language):
    return CASES if language == 'javascript' else {**CASES, **TS_CASES}


def _spec(language, name):
    """The specifier each language spells: JS names the file, TS resolves the extension."""
    return f'./{name}.js' if language == 'javascript' else f'./{name}'


def _importer(language):
    return ''.join(template.format(m=_spec(language, name), n=i) + '\n'
                   for i, (name, (template, _s, _d)) in enumerate(_cases(language).items()))


def _write(root, files):
    root.mkdir()
    root = root.resolve()  # macOS tmp is /private/var
    for rel, text in files.items():
        (root / rel).write_text(text, encoding='utf-8')
    return root


@pytest.fixture(autouse=True)
def _no_disk_cache(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')


def _json(uri):
    out = _run_reveal_direct(uri, '--format', 'json')
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.parametrize('language', sorted(LANGUAGES))
def test_importer_parses_cleanly(language):
    """Positive control: no case is recovered from an ERROR node."""
    root = tree_root(ts_parse(ts.get_parser(language), _importer(language)))
    assert not _zero_arg(root, 'has_error')


@pytest.mark.parametrize('language', sorted(LANGUAGES))
def test_extractor_records_scope_and_dynamic(tmp_path, language):
    ext = LANGUAGES[language]
    path = _write(tmp_path / 'x', {f'm{ext}': _importer(language)}) / f'm{ext}'
    found = {stmt.module_name[2:].removesuffix('.js'): (stmt.scope, stmt.dynamic)
             for stmt in extract_js_imports(path)}
    assert found == {name: (scope, dynamic) for name, (_t, scope, dynamic) in _cases(language).items()}


@pytest.mark.parametrize('language', sorted(LANGUAGES))
def test_lazy_views_split_edges_by_scope(tmp_path, language):
    ext = LANGUAGES[language]
    cases = _cases(language)
    files = {f'{name}{ext}': 'export const x = 1;\n' for name in cases}
    root = _write(tmp_path / 'p', {**files, f'm{ext}': _importer(language)})
    by_lazy = {}
    for lazy in ('include', 'exclude', 'only'):
        data = _json(f'imports://{to_posix(root)}?rank=fan-in&lazy={lazy}')
        by_lazy[lazy] = {to_posix(e['file'])[:-len(ext)] for e in data['entries'] if e['fan_in']}
        rule = data['edge_rule']
        assert (rule['unclassified_edges'], rule['unclassified_languages']) == (0, []), lazy
        assert 'not recorded' not in rule['text']
    assert by_lazy == {
        'include': set(cases),
        'exclude': {name for name, (_t, scope, _d) in cases.items() if scope == M},
        'only': {name for name, (_t, scope, _d) in cases.items() if scope == L},
    }


# a imports b at module level; b imports a back only inside a function: no load-time cycle.
LAZY_BACK_EDGE = {
    'javascript': {'a.js': "import { y } from './b.js';\nexport const x = 1;\n",
                   'b.js': "export const y = 2;\nexport function f() { return import('./a.js'); }\n"},
    'typescript': {'a.ts': "import { y } from './b';\nexport const x = 1;\n",
                   'b.ts': "export const y = 2;\nexport const f = function () { return require('./a'); };\n"},
    'tsx': {'a.tsx': "import { y } from './b';\nexport const x = 1;\n",
            'b.tsx': "export const y = 2;\nexport class K { m() { return import('./a'); } }\n"},
}
# Control: the same pair with the back-edge at module level (dynamic import included).
EAGER_BACK_EDGE = {
    'javascript': {'a.js': "import { y } from './b.js';\nexport const x = 1;\n",
                   'b.js': "export const y = 2;\nimport('./a.js');\n"},
    'typescript': {'a.ts': "import { y } from './b';\nexport const x = 1;\n",
                   'b.ts': "import { x } from './a';\nexport const y = x;\n"},
    'tsx': {'a.tsx': "import { y } from './b';\nexport const x = 1;\n",
            'b.tsx': "export const y = 2;\nexport class K { static z = require('./a'); }\n"},
}


def _cycles(root, extra=''):
    data = _json(f'imports://{to_posix(root)}?circular{extra}')
    return data['count'], data['metadata']['has_cycles']


@pytest.mark.parametrize('language', sorted(LANGUAGES))
def test_lazy_back_edge_is_not_a_cycle(tmp_path, language):
    root = _write(tmp_path / 'lazy', LAZY_BACK_EDGE[language])
    assert _cycles(root) == (0, False)
    assert _cycles(root, '&lazy=include') == (1, True), 'positive control: the back-edge is real'


@pytest.mark.parametrize('language', sorted(LANGUAGES))
def test_module_level_cycle_is_still_reported(tmp_path, language):
    root = _write(tmp_path / 'eager', EAGER_BACK_EDGE[language])
    assert _cycles(root) == (1, True)
    assert _cycles(root, '&lazy=only') == (0, False)


@pytest.mark.parametrize('language', ['typescript', 'tsx'])
def test_type_only_import_cycle_is_unchanged(tmp_path, language):
    """``import type`` is a module-scope edge, so a cycle through it is reported, as before."""
    ext = LANGUAGES[language]
    root = _write(tmp_path / 'typed', {
        f'a{ext}': "import type { Y } from './b';\nexport type X = { y?: Y };\n",
        f'b{ext}': "import type { X } from './a';\nexport type Y = { x?: X };\n",
    })
    assert _cycles(root) == (1, True)
