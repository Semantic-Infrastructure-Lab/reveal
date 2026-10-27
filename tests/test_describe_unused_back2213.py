"""describe_unused names the unused symbols of a from-import, never of a whole-module import (BACK-2213 R7)."""
import pytest

from reveal.analyzers.imports.unused import describe_unused


@pytest.mark.parametrize('record, label', [
    pytest.param({'module': 'os', 'names': [], 'unused_names': ['os']}, 'os', id='py-import-os'),
    pytest.param({'module': 'os.path', 'names': [], 'unused_names': ['osp']}, 'os.path', id='py-import-as'),
    pytest.param({'module': 'net/http', 'names': ['http'], 'unused_names': ['http']}, 'net/http', id='go-whole-module'),
    pytest.param({'module': 'os', 'names': ['path'], 'unused_names': ['path']}, 'os (unused: path)',
                 id='py-from-import-all-unused'),
    pytest.param({'module': 'typing', 'names': ['Dict', 'Any', 'List'], 'unused_names': ['Dict', 'Any']},
                 'typing (unused: Dict, Any)', id='py-from-import-partly-used'),
    pytest.param({'module': 'react', 'names': ['React'], 'unused_names': ['React']}, 'react (unused: React)',
                 id='js-default-import'),
    pytest.param({'module': 'y', 'names': ['*'], 'unused_names': ['ns']}, 'y (unused: ns)', id='js-namespace'),
    pytest.param({'module': 'm', 'unused_names': []}, 'm', id='no-names'),
])
def test_label(record, label):
    assert describe_unused(record) == label
