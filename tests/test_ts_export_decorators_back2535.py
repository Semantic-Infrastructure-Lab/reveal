"""BACK-2535: a decorator written before ``export class`` belongs to the class.

tree-sitter puts it on the ``export_statement``, a sibling of the class node, so
``@Component(...) export class Widget`` read no decorators (the Angular and NestJS form).
"""
import json

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

SOURCE = (
    '@Component({selector: "x"})\nexport class Widget {}\n\n'
    '@Controller("y")\nexport default class Api {\n  @Get()\n  list() { return 1; }\n}\n\n'
    '@Injectable()\nexport abstract class Base {}\n\n'
    '@Pipe()\nclass Local {}\n\n'
    'export class Plain {}\n'
)


@pytest.fixture
def decorators(tmp_path):
    path = tmp_path / 'w.ts'
    path.write_text(SOURCE, encoding='utf-8')
    data = json.loads(_run_reveal_direct(f'ast://{path}', '--format', 'json').stdout)
    return {r['name']: r.get('decorators') for r in data['results']}


def test_exported_classes_keep_their_decorators(decorators):
    assert decorators['Widget'] == ['@Component({selector: "x"})']
    assert decorators['Api'] == ['@Controller("y")']
    assert decorators['Base'] == ['@Injectable()']


def test_controls(decorators):
    assert decorators['Local'] == ['@Pipe()']   # not exported: worked before
    assert decorators['list'] == ['@Get()']     # member decorator: worked before
    assert decorators['Plain'] == []            # no decorator


def test_decorator_filter_finds_the_exported_class(tmp_path):
    path = tmp_path / 'w.ts'
    path.write_text(SOURCE, encoding='utf-8')
    data = json.loads(_run_reveal_direct(f'ast://{path}?decorator=Component', '--format', 'json').stdout)
    assert [r['name'] for r in data['results']] == ['Widget']
