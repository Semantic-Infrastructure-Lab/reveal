"""BACK-2491: D001 compares function bodies inside one type, not across types.

A rule census at d22a74c3 found 231 D001 claims in ripgrep's ``crates/core/flags/defs.rs``
(``is_switch``/``doc_category`` of ~100 ``impl Flag for X`` blocks) and 3,008 in Guava.
The rule grouped bodies by the first ``structure['classes']`` entry whose line range held
the function: Rust has no ``classes`` (every impl method fell into one module scope), and a
nested class's methods landed in the outermost class. The structure already records each
function's ``owner`` (the impl's Self type, ``Outer.Inner``) from the tree; that is the scope.

Second cause: a Rust trait default (``fn name_short(&self) -> Option<u8> { None }``) ends in a
bare tail expression, which the trivial-hook exemption (BACK-1049) did not recognise as the
``return None`` it is.

Still open (needs analyzer structure, not changed here): Java enum-constant bodies and
anonymous classes have no owner of their own, so their methods share the enclosing type's
scope; the strict xfails below pin that gap.
"""

import pytest

from reveal.rules.duplicates import _bodies
from reveal.rules.duplicates.D001 import D001

pytestmark = pytest.mark.component


def _detect(tmp_path, source, name):
    path = tmp_path / name
    path.write_text(source, encoding='utf-8')
    from reveal.registry import get_analyzer
    structure = get_analyzer(str(path))(str(path)).get_structure()
    return D001().check(str(path), structure, source)


def _pairs(detections):
    """(duplicate, original) names per detection."""
    return [tuple(d.message.split("'")[1:4:2]) for d in detections]


# --- the census shape: trait impls on different types ----------------------------------

RUST_TRAIT_IMPLS = '''trait Flag {
    fn is_switch(&self) -> bool;
    fn doc_category(&self) -> Category;
}

struct AfterContext;

impl Flag for AfterContext {
    fn is_switch(&self) -> bool {
        false
    }
    fn doc_category(&self) -> Category {
        Category::Output
    }
}

struct BeforeContext;

impl Flag for BeforeContext {
    fn is_switch(&self) -> bool {
        false
    }
    fn doc_category(&self) -> Category {
        Category::Output
    }
}

struct Context;

impl Flag for Context {
    fn is_switch(&self) -> bool {
        false
    }
    fn doc_category(&self) -> Category {
        Category::Output
    }
}
'''


def test_rust_trait_impls_on_different_types_are_not_duplicates(tmp_path):
    assert _detect(tmp_path, RUST_TRAIT_IMPLS, 'defs.rs') == []


RUST_TRAIT_DEFAULTS = '''trait Matcher {
    fn capture_index(&self, _name: &str) -> Option<usize> {
        None
    }

    fn non_matching_bytes(&self) -> Option<&ByteSet> {
        None
    }

    fn is_empty(&self) -> bool {
        false
    }

    fn is_sorted(&self) -> bool {
        false
    }
}
'''


def test_rust_tail_expression_hook_defaults_are_not_duplicates(tmp_path):
    assert _detect(tmp_path, RUST_TRAIT_DEFAULTS, 'lib.rs') == []


# --- nested classes are their own scope ---------------------------------------------------

JAVA_NESTED = '''class Outer {
    final class KeySet {
        @Override
        public void clear() {
            Outer.this.clear();
        }
    }

    final class Values {
        @Override
        public void clear() {
            Outer.this.clear();
        }
    }

    public void clear() {
        table.clear();
    }
}
'''


def test_java_sibling_nested_classes_are_not_compared(tmp_path):
    assert _detect(tmp_path, JAVA_NESTED, 'Outer.java') == []


PY_NESTED = '''class Outer:
    class First:
        def connect(self, *args, **kwargs):
            raise RuntimeError("unexpected error")

    class Second:
        def connect(self, *args, **kwargs):
            raise RuntimeError("unexpected error")
'''


def test_python_sibling_nested_classes_are_not_compared(tmp_path):
    assert _detect(tmp_path, PY_NESTED, 'nested.py') == []


# --- controls: real copy-paste inside one scope is still reported --------------------------

RUST_SAME_IMPL = '''struct Handle;

impl Handle {
    fn read_write(&self) -> Result<&Database> {
        match self {
            Handle::ReadWrite(database) => Ok(database),
            Handle::ReadOnly(_) => bail!("index was opened read-only"),
        }
    }

    fn read_write_again(&self) -> Result<&Database> {
        match self {
            Handle::ReadWrite(database) => Ok(database),
            Handle::ReadOnly(_) => bail!("index was opened read-only"),
        }
    }
}
'''


def test_rust_copy_paste_inside_one_impl_is_reported(tmp_path):
    assert _pairs(_detect(tmp_path, RUST_SAME_IMPL, 'index.rs')) == [('read_write_again', 'read_write')]


RUST_FREE = '''fn usize(v: &OsStr) -> Result<usize> {
    str(v)?.parse().context("value is not a valid number")
}

fn u64(v: &OsStr) -> Result<u64> {
    str(v)?.parse().context("value is not a valid number")
}
'''


def test_rust_copy_paste_free_functions_is_reported(tmp_path):
    assert _pairs(_detect(tmp_path, RUST_FREE, 'convert.rs')) == [('u64', 'usize')]


def test_rust_same_impl_split_over_two_blocks_is_one_scope(tmp_path):
    source = RUST_SAME_IMPL.replace(
        '    }\n\n    fn read_write_again', '    }\n}\n\nimpl Handle {\n    fn read_write_again')
    assert source.count('impl Handle') == 2
    assert _pairs(_detect(tmp_path, source, 'index.rs')) == [('read_write_again', 'read_write')]


JAVA_SAME_CLASS = '''class Stats {
    public static Stats of(DoubleStream values) {
        return values
            .collect(StatsAccumulator::new, StatsAccumulator::add, StatsAccumulator::addAll)
            .snapshot();
    }

    public static Stats of(LongStream values) {
        return values
            .collect(StatsAccumulator::new, StatsAccumulator::add, StatsAccumulator::addAll)
            .snapshot();
    }
}
'''


def test_java_copy_paste_inside_one_class_is_reported(tmp_path):
    assert _pairs(_detect(tmp_path, JAVA_SAME_CLASS, 'Stats.java')) == [('of', 'of')]


def test_java_copy_paste_inside_one_nested_class_is_reported(tmp_path):
    nested = 'class Outer {\n' + JAVA_SAME_CLASS.replace('class Stats', 'static final class Stats') + '}\n'
    assert _pairs(_detect(tmp_path, nested, 'Outer.java')) == [('of', 'of')]


RUBY_DUP = '''class Svc
  def first(key)
    value = lookup(key)
    return fallback if value.nil?
    value
  end

  def second(key)
    value = lookup(key)
    return fallback if value.nil?
    value
  end
end
'''

LUA_DUP = '''local M = {}

function M.first(key)
  local value = lookup(key)
  if value == nil then return fallback end
  return value
end

function M.second(key)
  local value = lookup(key)
  if value == nil then return fallback end
  return value
end

local function hook_a()
  return nil
end

local function hook_b()
  return nil
end

return M
'''


@pytest.mark.parametrize('name,source,expected', [
    ('svc.rb', RUBY_DUP, [('second', 'first')]),
    ('m.lua', LUA_DUP, [('second', 'first')]),
])
def test_languages_d001_is_not_aimed_at_keep_their_claims(tmp_path, name, source, expected):
    assert _pairs(_detect(tmp_path, source, name)) == expected


# --- trivial-body exemption: a bare tail value is the `return <value>` hook ---------------

@pytest.mark.parametrize('body', [
    'None', 'false', 'true', 'nil', '0', '()', '[]', '{}', 'None\n}', 'false;',
])
def test_bare_tail_value_is_a_trivial_hook_body(body):
    assert _bodies.is_trivial_hook_body(body)


@pytest.mark.parametrize('body', [
    'Category::Output', 'Some(1)', 'Ok(())', 'self.x', 'x', '-1', 'None\nfalse', 'Nothing',
])
def test_computed_or_wrapped_tail_is_not_a_trivial_hook_body(body):
    assert not _bodies.is_trivial_hook_body(body)


# --- open gap: scopes the structure does not carry (needs analyzer work) ------------------

JAVA_ENUM_CONSTANTS = '''enum CaseFormat {
    LOWER_HYPHEN {
        @Override
        String normalizeWord(String word) {
            return Ascii.toLowerCase(word);
        }
    },

    LOWER_UNDERSCORE {
        @Override
        String normalizeWord(String word) {
            return Ascii.toLowerCase(word);
        }
    };

    abstract String normalizeWord(String word);
}
'''

JAVA_ANONYMOUS = '''class CacheTest {
    void testA() {
        CacheLoader<Object, Object> loader =
            new CacheLoader<Object, Object>() {
                @Override
                public Object load(Object key) {
                    throw new AssertionError();
                }
            };
    }

    void testB() {
        CacheLoader<Object, Object> loader =
            new CacheLoader<Object, Object>() {
                @Override
                public Object load(Object key) {
                    throw new AssertionError();
                }
            };
    }
}
'''


@pytest.mark.xfail(strict=True, reason='BACK-2491: enum-constant and anonymous class bodies have no '
                   'owner in the structure, so D001 cannot tell them apart (analyzer change proposed)')
@pytest.mark.parametrize('name,source', [('CaseFormat.java', JAVA_ENUM_CONSTANTS),
                                         ('CacheTest.java', JAVA_ANONYMOUS)])
def test_java_bodies_without_their_own_owner_are_not_compared(tmp_path, name, source):
    assert _detect(tmp_path, source, name) == []
