"""BACK-2263: contracts:// reads class decorators through the shared conventions owner, so a C#
attribute list gives one name per attribute (``[ApiController, Route("x")]`` -> ``ApiController``,
``Route``) instead of source fragments (``[ApiController, Route``); Python names are unchanged."""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component


def _decorators(tmp_path, name, source, cls):
    (tmp_path / name).write_text(source, encoding='utf-8')
    data = json.loads(_run_reveal_direct(f'contracts://{tmp_path}', '--format', 'json').stdout)
    rows = [row for key in ('abcs', 'protocols', 'typeddicts', 'dataclasses', 'basemodels', 'path_heuristic')
            for row in data.get(key, []) if row['name'] == cls]
    assert rows, data
    return rows[0]['decorators']


def test_csharp_attribute_list(tmp_path):
    source = ('namespace N {\n  [ApiController, Route("api/x")]\n  [Serializable]\n'
              '  public class FooController : ControllerBase { }\n}\n')
    assert _decorators(tmp_path, 'Foo.cs', source, 'FooController') == ['ApiController', 'Route', 'Serializable']


def test_python_dataclass_still_classified(tmp_path):
    source = 'import dataclasses\n\n@dataclasses.dataclass(frozen=True)\nclass P:\n    x: int\n'
    (tmp_path / 'p.py').write_text(source, encoding='utf-8')
    data = json.loads(_run_reveal_direct(f'contracts://{tmp_path}', '--format', 'json').stdout)
    assert [row['decorators'] for row in data['dataclasses'] if row['name'] == 'P'] == [['dataclasses.dataclass']]


def test_typescript_decorator_with_object_argument(tmp_path):
    # Not exported: a decorator before `export class` is not extracted at all (separate task).
    source = '@Component({selector: "x"})\nclass Widget implements OnInit {}\n'
    assert _decorators(tmp_path, 'w.ts', source, 'Widget') == ['Component']
