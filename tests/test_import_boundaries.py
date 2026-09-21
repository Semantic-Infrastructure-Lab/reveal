"""Import-boundary guards: the analyzer core must not load the adapters (BACK-1359).

`import reveal.treesitter` used to load 303 reveal modules, 169 of them
adapters (mysql, ssl, ...), because treesitter.py imported its node-kind
taxonomy from the reveal.adapters.ast re-export shim instead of reveal.core.
Cost: every process paid for the whole adapter graph, and an adapter's
optional-dependency failure could break the core analyzer.

Each check runs in a fresh interpreter: this pytest process has already
imported everything, so sys.modules here says nothing about a cold import.
"""

import json
import subprocess
import sys

import pytest

# Entry points that must stay adapter-free. reveal/__init__.py runs first for
# all of them, so this covers the package import as well.
_CORE_ENTRY_POINTS = [
    'reveal.treesitter',
    'reveal.analyzers.python',
    'reveal.core.node_taxonomy',
    'reveal.complexity',
]

_PROBE = (
    "import json, sys, {module}\n"
    "print(json.dumps(sorted(k for k in sys.modules "
    "if k == 'reveal.adapters' or k.startswith('reveal.adapters.'))))\n"
)


def _loaded_adapter_modules(module: str) -> list:
    proc = subprocess.run(
        [sys.executable, '-c', _PROBE.format(module=module)],
        capture_output=True,
        check=False,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=120,
    )
    assert proc.returncode == 0, f"import {module} failed:\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize('module', _CORE_ENTRY_POINTS)
def test_core_import_does_not_load_adapters(module):
    loaded = _loaded_adapter_modules(module)
    assert loaded == [], (
        f"`import {module}` loaded {len(loaded)} adapter module(s), e.g. "
        f"{loaded[:5]}. The analyzer core must import from reveal.core, not "
        f"reveal.adapters (BACK-1359)."
    )


def test_node_taxonomy_shim_reexports_core_objects():
    """The adapters.ast shim stays a pure re-export, so old imports keep working."""
    from reveal.adapters.ast import node_taxonomy as shim
    from reveal.core import node_taxonomy as core

    for name in ('DEF_NODES', 'CLASS_NODES', 'STRUCT_NODES', 'IMPORT_NODES'):
        assert getattr(shim, name) is getattr(core, name)


def test_treesitter_node_type_constants_derive_from_core_taxonomy():
    from reveal import treesitter
    from reveal.core import node_taxonomy as core

    assert set(treesitter.FUNCTION_NODE_TYPES) == set(core.DEF_NODES) - {'arrow_function'}
    assert set(treesitter.CLASS_NODE_TYPES) == set(core.CLASS_NODES)
    assert set(treesitter.STRUCT_NODE_TYPES) == set(core.STRUCT_NODES)
    assert set(treesitter.IMPORT_NODE_TYPES) == set(core.IMPORT_NODES)
    assert treesitter.ELEMENT_TYPE_MAP == {
        'function': treesitter.FUNCTION_NODE_TYPES,
        'class': treesitter.CLASS_NODE_TYPES,
        'struct': treesitter.STRUCT_NODE_TYPES,
    }
