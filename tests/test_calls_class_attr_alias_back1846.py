"""BACK-1846: a class body that rebinds an import alias makes ``self.X()`` a call of the original.

celery/utils/timer2.py::

    from kombu.asynchronous.timer import Timer as Schedule
    class Timer(threading.Thread):
        Schedule = Schedule
        def __init__(self, ...):
            self.schedule = self.Schedule(...)

BACK-1833 limited import aliases to bare calls (``o.h()`` is a method named h, not ``m.helper``),
which also dropped this true edge: the recall gate's Python callers population fell from 1046 to
1045. The alias applies to ``self.X`` / ``cls.X`` only inside the class whose body binds it.
"""
from pathlib import Path

import pytest

from reveal.adapters.calls.index import find_callers

pytestmark = pytest.mark.component


def _callers(directory, target):
    result = find_callers(str(directory), target)
    return {(Path(c['file']).name, c['caller'])
            for level in result['levels'] for c in level['callers']}


def _project(tmp_path):
    (tmp_path / 'timer.py').write_text('class Timer:\n    pass\n', encoding='utf-8')
    (tmp_path / 'app.py').write_text(
        'from timer import Timer as Schedule\n\n'
        'class Runner:\n'
        '    Schedule = Schedule\n\n'
        '    def __init__(self):\n        self.schedule = self.Schedule()\n\n'
        '    @classmethod\n'
        '    def build(cls):\n        return cls.Schedule()\n\n'
        'class Other:\n'
        '    def __init__(self):\n        self.s = self.Schedule()\n\n'
        'def member(o):\n    return o.Schedule()\n', encoding='utf-8')
    return tmp_path


def test_self_call_through_class_body_alias_reaches_the_original(tmp_path):
    assert ('app.py', '__init__') in _callers(_project(tmp_path), 'Timer')


def test_cls_call_through_class_body_alias_reaches_the_original(tmp_path):
    assert ('app.py', 'build') in _callers(_project(tmp_path), 'Timer')


def test_self_call_in_a_class_without_the_binding_is_not_a_caller(tmp_path):
    callers = _callers(_project(tmp_path), 'Timer')
    # Runner.__init__ is a caller; Other.__init__ (line 14) has no `Schedule = Schedule` binding.
    result = find_callers(str(tmp_path), 'Timer')
    lines = {c['line'] for level in result['levels'] for c in level['callers']
             if c['caller'] == '__init__'}
    assert lines == {6}
    assert ('app.py', 'member') not in callers


def test_attribute_name_still_indexes_the_attribute(tmp_path):
    callers = _callers(_project(tmp_path), 'Schedule')
    assert {('app.py', '__init__'), ('app.py', 'build'), ('app.py', 'member')} <= callers


def test_typescript_member_call_is_still_not_a_caller(tmp_path):
    # Negative control in another language: the class-body rule is Python-only, so BACK-1833's
    # TypeScript behaviour (a member call named like the alias is not a caller) is unchanged.
    (tmp_path / 'm.ts').write_text('export class Timer {}\n', encoding='utf-8')
    (tmp_path / 'app.ts').write_text(
        "import { Timer as Schedule } from './m';\n"
        'export function member(o: any) { return o.Schedule(); }\n'
        'export function direct() { return new Schedule(); }\n', encoding='utf-8')
    assert ('app.ts', 'member') not in _callers(tmp_path, 'Timer')
