"""ast://?decorator= matches bracket-style attributes by name (BACK-1777).

C# ``[HttpGet]``, PHP ``#[Route("/x")]`` and Rust ``#[derive(Debug)]`` are extracted into
an element's ``decorators`` with their brackets kept, and the filter compared that raw text
with an ``@``-prefixed target, so ``decorator=HttpGet``/``Route``/``derive`` found nothing.

The matching contract these tests pin:

- A captured decorator holds one or more attributes: ``@foo(...)`` holds one,
  ``[A, B(x)]`` and ``#[A, B]`` hold one per top-level comma. A bracketed group's
  attributes match one by one.
- A query term is matched against each attribute's NAME: the text before its arguments,
  with ``::`` and ``\\`` read as ``.``, a leading ``\\`` and a C#/Kotlin target
  (``return:``, ``field:``) dropped. The term may be qualified: it matches when its
  segments are the trailing segments of the name, so ``Obsolete`` and ``System.Obsolete``
  both match ``[System.Obsolete]``, but ``Http`` does not match ``HttpGet``.
- The term may be typed as in source: ``[HttpGet]``, ``#[Route]``, ``@Override``.
- A term with arguments (``HttpGet("{id}")``) matches only an attribute with that name and
  the same arguments, ignoring whitespace.
- A comma list is OR, as for every other ast:// filter: ``decorator=[HttpGet, Authorize]``
  finds methods carrying either.
- Rust ``#[derive(Debug, Clone)]`` is ONE attribute named ``derive``; ``Debug`` is its
  argument, not an attribute, so ``decorator=Debug`` finds nothing and
  ``decorator=*Debug*`` (a glob, matched against the source text too) finds the struct.
"""

from pathlib import Path

import pytest

from reveal.adapters.ast.adapter import AstAdapter

CONTROLLER_CS = '''\
using System;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Shop.Api.Controllers
{
    [ApiController]
    [Route("api/[controller]")]
    public class OrdersController : ControllerBase
    {
        private readonly IOrderService _orders;

        public OrdersController(IOrderService orders)
        {
            _orders = orders;
        }

        [HttpGet]
        public IActionResult List()
        {
            return Ok(_orders.All());
        }

        [HttpGet("{id}"), Authorize]
        public IActionResult Get(int id)
        {
            return Ok(_orders.Find(id));
        }

        [HttpPost, Authorize(Roles = "admin")]
        public IActionResult Create(Order order)
        {
            _orders.Add(order);
            return Ok();
        }

        [System.Obsolete("use Create")]
        public IActionResult CreateLegacy(Order order)
        {
            return Ok();
        }

        [return: NotNull]
        public string Describe()
        {
            return "orders";
        }

        private void Helper()
        {
        }
    }

    [ApiController]
    [Route("api/customers")]
    public class CustomersController : ControllerBase
    {
        [HttpDelete("{id}")]
        public IActionResult Delete(int id)
        {
            return NoContent();
        }
    }

    public class Order
    {
        public int Id { get; set; }
    }
}
'''

ROUTES_PHP = '''\
<?php
#[Route("/x")]
class Routes
{
    #[Route("/a"), Deprecated]
    public function a() {}

    #[\\Symfony\\Component\\Routing\\Attribute\\Route("/b")]
    public function b() {}

    public function plain() {}
}
'''

MODEL_RS = '''\
#[derive(Debug, Clone)]
struct Point { x: i32 }

#[test]
fn unit() {}

#[tokio::test(flavor = "multi_thread")]
async fn async_unit() {}

fn plain() {}
'''

AT_STYLE = {
    'A.java': '''\
package x;
public class A {
  @Override
  public String toString() { return ""; }
  @SuppressWarnings("unchecked")
  void suppressed() {}
  @org.junit.Test
  void junit() {}
  void plain() {}
}
''',
    'B.ts': '''\
@Component({selector: 'x'})
class B {
  @Input() name() { return 1; }
  plain() { return 2; }
}
''',
    'C.swift': '''\
class C {
  @available(iOS 13, *)
  func gated() {}
  @objc func bridged() {}
  func plain() {}
}
''',
    'D.kt': '''\
class D {
  @Deprecated("x")
  fun old() {}
  @Test fun check() {}
  fun plain() {}
}
''',
    'e.py': '''\
import functools
class E:
    @property
    def prop(self): return 1
    @functools.lru_cache(maxsize=10)
    def cached(self): return 2
    @app.route('/x', methods=['GET'])
    def handler(self): return 3
    @router
    def routed(self): pass
    def plain(self): pass
''',
}


def _write(directory: Path, files: dict) -> Path:
    directory.mkdir()
    for name, text in files.items():
        (directory / name).write_text(text, encoding='utf-8')
    return directory


@pytest.fixture(scope='module')
def tree(tmp_path_factory):
    root = tmp_path_factory.mktemp('back1777')
    return {
        'cs': _write(root / 'cs', {'OrdersController.cs': CONTROLLER_CS}),
        'php': _write(root / 'php', {'Routes.php': ROUTES_PHP}),
        'rs': _write(root / 'rs', {'model.rs': MODEL_RS}),
        'at': _write(root / 'at', AT_STYLE),
    }


def _names(path: Path, query: str) -> set:
    result = AstAdapter(str(path), query).get_structure()
    return {r['name'] for r in result['results']}


class TestCSharpController:
    """A multi-class ASP.NET controller file: brackets, arguments, groups, targets."""

    def test_extraction_keeps_the_source_text(self, tree):
        # Sibling control: the extraction side is right and unchanged; only matching was wrong.
        result = AstAdapter(str(tree['cs']), 'name=Create').get_structure()
        assert result['results'][0]['decorators'] == ['[HttpPost, Authorize(Roles = "admin")]']

    @pytest.mark.parametrize('query, expected', [
        ('decorator=HttpGet', {'List', 'Get'}),
        ('decorator=[HttpGet]', {'List', 'Get'}),
        ('decorator=HttpPost', {'Create'}),
        ('decorator=HttpDelete', {'Delete'}),
        ('decorator=Authorize', {'Get', 'Create'}),
        ('decorator=ApiController', {'OrdersController', 'CustomersController'}),
        ('decorator=Route', {'OrdersController', 'CustomersController'}),
        ('decorator=NotNull', {'Describe'}),
    ])
    def test_bare_and_bracketed_names(self, tree, query, expected):
        assert _names(tree['cs'], query) == expected

    @pytest.mark.parametrize('query, expected', [
        ('decorator=Obsolete', {'CreateLegacy'}),
        ('decorator=System.Obsolete', {'CreateLegacy'}),
        ('decorator=Other.Obsolete', set()),
    ])
    def test_qualified_names_match_by_trailing_segments(self, tree, query, expected):
        assert _names(tree['cs'], query) == expected

    def test_arguments_in_the_term_must_match(self, tree):
        assert _names(tree['cs'], 'decorator=HttpGet("{id}")') == {'Get'}
        assert _names(tree['cs'], 'decorator=Route("api/customers")') == {'CustomersController'}

    def test_comma_list_is_or(self, tree):
        assert _names(tree['cs'], 'decorator=[HttpGet, Authorize]') == {'List', 'Get', 'Create'}
        assert _names(tree['cs'], 'decorator=HttpPost,HttpDelete') == {'Create', 'Delete'}

    def test_glob_matches_attribute_names(self, tree):
        assert _names(tree['cs'], 'decorator=Http*') == {'List', 'Get', 'Create', 'Delete'}

    def test_no_prefix_or_substring_match(self, tree):
        # Negative control: a name match is whole-segment, never a prefix.
        assert _names(tree['cs'], 'decorator=Http') == set()
        assert _names(tree['cs'], 'decorator=Get') == set()

    def test_glob_on_source_text_still_works(self, tree):
        # Passes on master too: the raw-text glob is kept for back-compatibility.
        assert _names(tree['cs'], 'decorator=*HttpGet*') == {'List', 'Get'}


class TestPhpAttributes:
    @pytest.mark.parametrize('query, expected', [
        ('decorator=Route', {'Routes', 'a', 'b'}),
        ('decorator=#[Route("/x")]', {'Routes'}),
        ('decorator=Route("/a")', {'a'}),
        ('decorator=Deprecated', {'a'}),
        ('decorator=Attribute\\Route', {'b'}),
        ('decorator=Other\\Route', set()),
    ])
    def test_php_attributes(self, tree, query, expected):
        assert _names(tree['php'], query) == expected


class TestRustAttributes:
    @pytest.mark.parametrize('query, expected', [
        ('decorator=derive', {'Point'}),
        ('decorator=#[derive]', {'Point'}),
        ('decorator=test', {'unit', 'async_unit'}),
        ('decorator=tokio::test', {'async_unit'}),
    ])
    def test_rust_attributes(self, tree, query, expected):
        assert _names(tree['rs'], query) == expected

    def test_derive_arguments_are_not_attributes(self, tree):
        # The chosen contract: `Debug` is an argument of `derive`, found by a source glob.
        assert _names(tree['rs'], 'decorator=Debug') == set()
        assert _names(tree['rs'], 'decorator=*Debug*') == {'Point'}


class TestAtStyleControls:
    """Negative controls: at-style languages that already worked keep their answers."""

    @pytest.mark.parametrize('query, expected', [
        ('decorator=Override', {'toString'}),
        ('decorator=@Override', {'toString'}),
        ('decorator=SuppressWarnings', {'suppressed'}),
        ('decorator=Input', {'name'}),
        ('decorator=Component', {'B'}),
        ('decorator=available', {'gated'}),
        ('decorator=objc', {'bridged'}),
        ('decorator=Deprecated', {'old'}),
        ('decorator=property', {'prop'}),
        ('decorator=@property', {'prop'}),
        ('decorator=app.route', {'handler'}),
        ('decorator=router', {'routed'}),
        ('decorator=*cache*', {'cached'}),
        ('decorator=prop', set()),
    ])
    def test_unchanged_answers(self, tree, query, expected):
        assert _names(tree['at'], query) == expected

    @pytest.mark.parametrize('query, expected', [
        # The qualified-name contract applied to at-style decorators.
        ('decorator=Test', {'check', 'junit'}),
        ('decorator=org.junit.Test', {'junit'}),
        ('decorator=route', {'handler'}),
        ('decorator=lru_cache', {'cached'}),
        ('decorator=lru_cache(maxsize=10)', {'cached'}),
        ('decorator=lru_cache(maxsize=11)', set()),
    ])
    def test_qualified_at_style(self, tree, query, expected):
        assert _names(tree['at'], query) == expected


class TestCallsEntryPoints:
    """The calls adapter's bare names come from the same parser: an action carrying a
    grouped `[HttpPost, Authorize]` is a framework entry point, not dead code."""

    def test_grouped_attribute_action_is_not_uncalled(self, tree):
        from reveal.adapters.calls.index import find_uncalled
        uncalled = {e['name'] for e in find_uncalled(str(tree['cs']))['entries']}
        assert 'Create' not in uncalled
        # Sibling controls: an undecorated private method stays a candidate, and a
        # single-attribute action stays excluded.
        assert 'Helper' in uncalled
        assert 'List' not in uncalled
