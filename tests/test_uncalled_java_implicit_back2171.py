"""?uncalled over Java leaves out what the JVM or a framework invokes by name (BACK-2171).

A BACK-1899 review of Guava found 68% of its claims were JUnit 3 `test*` methods in testlib
testers (classes deriving from TestCase, run reflectively), 127 were serialization hooks, and
`@Subscribe` / `@JsMethod` methods are dispatched by annotation. None is a call expression.
"""
import pytest

from reveal.adapters.calls.index import find_uncalled

pytestmark = pytest.mark.component

BASE = '''\
public abstract class AbstractTester extends TestCase {
  public void testBase() {}
  public void deadHelper() {}
}
'''
DERIVED = '''\
public class DerivedTester extends AbstractTester {
  public void testDerived() {}
}
'''
PLAIN = '''\
public class Plain {
  public void testNotInATestCase() {}
  public void orphan() {}
}
'''
HOOKS = '''\
public class Hooks implements java.io.Serializable {
  private Object readResolve() { return null; }
  private Object writeReplace() { return null; }
  private void readObject(java.io.ObjectInputStream in) {}
  private void writeObject(java.io.ObjectOutputStream out) {}
  public void readConfig() {}
  @Subscribe public void onEvent(String e) {}
  @JsMethod public void exported() {}
}
'''


def names(tmp_path, files, **kw):
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding='utf-8')
    return find_uncalled(str(tmp_path), **kw)


def reported(result):
    return sorted(e['name'] for e in result['entries'])


def test_junit3_test_methods_of_a_testcase_hierarchy_are_not_dead(tmp_path):
    result = names(tmp_path, {'AbstractTester.java': BASE, 'DerivedTester.java': DERIVED, 'Plain.java': PLAIN})
    assert reported(result) == ['deadHelper', 'orphan', 'testNotInATestCase']
    assert result['excluded_by_reason']['junit3_test'] == 2
    assert result['test_entrypoints_excluded'] >= 2


def test_include_test_framework_keeps_junit3_methods(tmp_path):
    result = names(tmp_path, {'AbstractTester.java': BASE, 'DerivedTester.java': DERIVED},
                   include_test_framework=True)
    assert 'testBase' in reported(result) and 'testDerived' in reported(result)


def test_serialization_hooks_and_annotation_dispatch_are_not_dead(tmp_path):
    assert reported(names(tmp_path, {'Hooks.java': HOOKS})) == ['readConfig']


ANNOTATED = '''\
public class CacheGwtTest {
  @SuppressWarnings("deprecation")
  @Test
  public void loadingCache() {}

  @Test
  @J2ktIncompatible
  public void mapMethods() {}

  @SuppressWarnings({"a",
      "b"})
  @Test
  public void multiLine() {}

  public void orphan() {}
}
'''


def test_junit4_test_after_another_annotation_is_not_dead(tmp_path):
    """The claim line is the first annotation, so a marker scan from there never saw the @Test."""
    assert reported(names(tmp_path, {'CacheGwtTest.java': ANNOTATED})) == ['orphan']
