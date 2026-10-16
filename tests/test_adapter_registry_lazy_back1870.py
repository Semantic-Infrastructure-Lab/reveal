"""Shipped adapters import on first lookup of their scheme, not at `import reveal` (BACK-1870)."""

import json
import subprocess
import sys

import pytest

from reveal.adapters.registry import BUILTIN_SCHEMES


def _run(code: str) -> str:
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                         encoding='utf-8', check=True, env=_env())
    return out.stdout


def _env():
    # Children import the same checkout as this process, not whatever is installed.
    import os
    import reveal
    env = dict(os.environ)
    env['PYTHONPATH'] = os.path.dirname(os.path.dirname(reveal.__file__))
    return env


def _adapter_modules(code_after_import: str) -> list:
    return json.loads(_run(
        "import sys, json\n"
        "import reveal.main\n"
        + code_after_import +
        "\nprint(json.dumps(sorted(m.split('.')[2] for m in sys.modules"
        " if m.startswith('reveal.adapters.') and m.count('.') == 2)))"))


def test_startup_imports_no_pure_resource_adapter():
    loaded = _adapter_modules('')
    for heavy in ('domain', 'mysql', 'cpanel', 'xlsx', 'git', 'claude', 'autossl'):
        assert heavy not in loaded, loaded


def test_lookup_imports_only_that_adapter():
    loaded = _adapter_modules(
        "from reveal.adapters.registry import get_adapter_class\n"
        "assert get_adapter_class('env').__name__ == 'EnvAdapter'")
    assert 'env' in loaded
    assert 'domain' not in loaded and 'mysql' not in loaded


def test_enumeration_registers_exactly_the_builtin_schemes_in_order():
    got = json.loads(_run(
        "import json\n"
        "from reveal.adapters.registry import _ADAPTER_REGISTRY as A, list_renderer_schemes\n"
        "ast_first = A.get('ast') is not None\n"
        "print(json.dumps([list(A), ast_first, list_renderer_schemes()]))"))
    assert got[0] == list(BUILTIN_SCHEMES)
    assert got[1] is True
    assert got[2] == sorted(BUILTIN_SCHEMES)


def test_order_is_canonical_after_partial_load():
    got = json.loads(_run(
        "import json\n"
        "from reveal.adapters.registry import _ADAPTER_REGISTRY as A\n"
        "A['trace']; A['env']\n"
        "print(json.dumps(list(A)))"))
    assert got == list(BUILTIN_SCHEMES)


def test_package_attribute_returns_the_registered_class():
    from reveal import adapters
    from reveal.adapters.registry import get_adapter_class
    assert adapters.EnvAdapter is get_adapter_class('env')
    with pytest.raises(AttributeError):
        adapters.NoSuchAdapter


def test_unknown_scheme_is_none_and_loads_nothing_extra():
    from reveal.adapters.registry import get_adapter_class
    assert get_adapter_class('nope') is None


def test_startup_imports_none_of_the_optional_heavy_libraries():
    loaded = json.loads(_run(
        "import sys, json\n"
        "import reveal.main\n"
        "print(json.dumps(sorted({m.split('.')[0] for m in sys.modules} & "
        "{'cryptography', 'bs4', 'soupsieve', 'jsonschema', 'dns', 'pygit2'})))"))
    assert loaded == []


def test_file_handler_resolves_nginx_names_on_first_use():
    from reveal import file_handler
    from reveal.adapters.nginx import handlers
    assert file_handler.FlagOutput is handlers.FlagOutput
    assert file_handler._format_acl_col is handlers._format_acl_col
    emitting = file_handler._handle_diagnose
    assert emitting.__name__ == handlers._handle_diagnose.__name__
    assert file_handler._handle_diagnose is emitting  # cached, not rebuilt per access
    with pytest.raises(AttributeError):
        file_handler._not_a_handler


@pytest.mark.parametrize('flag', [
    ['--check-acl'], ['--check-conflicts'], ['--extract', 'domains'], ['--validate-nginx-acme'],
    ['--global-audit'], ['--cpanel-certs'], ['--diagnose'],
])
def test_every_lazy_nginx_flag_handler_runs_from_the_cli(flag):
    """_dispatch_special_flags calls the handlers by bare name: a module __getattr__ cannot
    serve those, so each flag must reach its handler without a NameError."""
    from pathlib import Path
    conf = Path(__file__).parent / 'fixtures' / 'formats' / 'nginx' / 'nginx.conf'
    out = subprocess.run([sys.executable, '-m', 'reveal', str(conf), *flag], capture_output=True,
                         text=True, encoding='utf-8', env=_env())
    assert 'Traceback' not in out.stderr and 'NameError' not in out.stderr, out.stderr
