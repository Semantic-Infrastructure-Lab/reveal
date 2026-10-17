"""The optional parse error hook observes only the existing failure boundary."""
import importlib
from unittest.mock import Mock, patch

import pytest

from reveal.adapters.ast import nav_surface_common as common
from reveal.adapters.ast.surface_matrix import UNPARSED_KEY

pytestmark = pytest.mark.component


@pytest.mark.parametrize('family', ['go', 'rust', 'ruby', 'cpp'])
def test_native_wrapper_forwards_only_actual_parse_failure(tmp_path, family):
    scanner = getattr(importlib.import_module('reveal.adapters.ast.nav_contracts_'+family),
                      'scan_file_contracts_'+family)
    file = tmp_path/'input.src'
    file.write_text('irrelevant\n', encoding='utf-8')
    error = OSError('exact parser failure')
    hook = Mock()
    with patch.object(common, 'get_tree', side_effect=error):
        result = scanner(str(file), on_error=hook)
    hook.assert_called_once_with(str(file), error)
    assert result[UNPARSED_KEY] == [str(file)]


def test_omitted_hook_preserves_surface_failure_shape_and_log(tmp_path, caplog):
    file = tmp_path/'sample.ts'
    file.write_text('irrelevant\n', encoding='utf-8')
    with patch.object(common, 'get_tree', side_effect=OSError('unchanged failure')):
        result = common.scan_file_with_grammar(str(file), 'typescript', 'TypeScript', Mock(), ['http'])
    assert result == {'http': [], UNPARSED_KEY: [str(file)]}
    assert 'unchanged failure' in caplog.text


def test_success_does_not_call_hook_or_change_clean_arrays(tmp_path):
    file = tmp_path/'sample.ts'
    file.write_text('interface Contract {}\n', encoding='utf-8')
    hook, scan = Mock(), Mock(return_value={'interfaces': [{'name': 'Contract', 'line': 1}]})
    result = common.scan_file_with_grammar(str(file), 'typescript', 'TypeScript', scan,
                                            ['interfaces'], on_error=hook)
    hook.assert_not_called()
    assert result == {'interfaces': [{'name': 'Contract', 'line': 1}]}


def test_callback_failure_is_not_swallowed(tmp_path):
    file = tmp_path/'sample.ts'
    file.write_text('irrelevant\n', encoding='utf-8')
    hook = Mock(side_effect=RuntimeError('callback bug'))
    with patch.object(common, 'get_tree', side_effect=OSError('parse failure')):
        with pytest.raises(RuntimeError, match='callback bug'):
            common.scan_file_with_grammar(str(file), 'typescript', 'TypeScript', Mock(),
                                           ['http'], on_error=hook)


def test_cpp_preparation_retains_clean_contract_and_omits_hook_call(tmp_path):
    from reveal.adapters.ast.nav_contracts_cpp import scan_file_contracts_cpp

    file = tmp_path/'contract.cpp'
    file.write_text('class ASSIMP_API Contract { public: virtual void go() = 0; };\n', encoding='utf-8')
    hook = Mock()
    result = scan_file_contracts_cpp(str(file), on_error=hook)
    hook.assert_not_called()
    assert result['classes'][0]['name'] == 'Contract'
    assert result['classes'][0]['is_abstract']
    assert all(not name.startswith('_') for name in result)
