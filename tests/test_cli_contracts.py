"""Tests for reveal contracts subcommand."""

import json
import os
import sys
import tempfile
import textwrap
import unittest
from argparse import Namespace
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from reveal.adapters.ast.analysis import collect_structures

from reveal.cli.commands.contracts import (
    _add_implementations,
    _extract_all_classes,
    _is_abc,
    _is_basemodel,
    _is_dataclass,
    _is_protocol,
    _is_typeddict,
    _render_report,
    _scan_contracts,
    create_contracts_parser,
    run_contracts,
)

# BACK-1149: component-layer test -- calls a reveal.cli.* handler function directly, not through reveal.main
pytestmark = pytest.mark.component


def _write(directory: str, filename: str, content: str) -> str:
    path = os.path.join(directory, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(textwrap.dedent(content))
    return path


class TestCreateContractsParser(unittest.TestCase):

    def test_parser_returns_parser(self):
        parser = create_contracts_parser()
        self.assertIsNotNone(parser)

    def test_defaults(self):
        parser = create_contracts_parser()
        args = parser.parse_args([])
        self.assertEqual(args.path, '.')
        self.assertFalse(args.abstract_only)
        self.assertFalse(args.no_implementations)

    def test_path_positional(self):
        parser = create_contracts_parser()
        args = parser.parse_args(['./src'])
        self.assertEqual(args.path, './src')

    def test_abstract_only_flag(self):
        parser = create_contracts_parser()
        args = parser.parse_args(['--abstract-only'])
        self.assertTrue(args.abstract_only)

    def test_no_implementations_flag(self):
        parser = create_contracts_parser()
        args = parser.parse_args(['--no-implementations'])
        self.assertTrue(args.no_implementations)


class TestClassifiers(unittest.TestCase):

    def test_is_abc_direct(self):
        self.assertTrue(_is_abc(['ABC']))

    def test_is_abc_qualified(self):
        self.assertTrue(_is_abc(['abc.ABC']))

    def test_is_abc_abcmeta(self):
        self.assertTrue(_is_abc(['ABCMeta']))

    def test_is_abc_false(self):
        self.assertFalse(_is_abc(['BaseModel', 'Protocol']))

    def test_is_protocol(self):
        self.assertTrue(_is_protocol(['Protocol']))
        self.assertTrue(_is_protocol(['typing.Protocol']))

    def test_is_protocol_false(self):
        self.assertFalse(_is_protocol(['ABC']))

    def test_is_typeddict(self):
        self.assertTrue(_is_typeddict(['TypedDict']))
        self.assertTrue(_is_typeddict(['typing.TypedDict']))

    def test_is_typeddict_false(self):
        self.assertFalse(_is_typeddict(['dict']))

    def test_is_dataclass(self):
        self.assertTrue(_is_dataclass(['dataclass']))
        self.assertTrue(_is_dataclass(['dataclasses.dataclass']))

    def test_is_dataclass_false(self):
        self.assertFalse(_is_dataclass(['property']))

    def test_is_basemodel(self):
        self.assertTrue(_is_basemodel(['BaseModel']))
        self.assertTrue(_is_basemodel(['BaseSettings']))

    def test_is_basemodel_false(self):
        self.assertFalse(_is_basemodel(['ABC']))


class TestExtractAllClasses(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_finds_abc_class(self):
        _write(self.tmp, 'base.py', '''\
            from abc import ABC, abstractmethod
            class MyBase(ABC):
                @abstractmethod
                def do_it(self): ...
        ''')
        structures = collect_structures(self.tmp)
        classes = _extract_all_classes(structures)
        self.assertEqual(len(classes), 1)
        self.assertEqual(classes[0]['name'], 'MyBase')
        self.assertIn('ABC', classes[0]['bases'])
        self.assertIn('do_it', classes[0]['abstract_methods'])

    def test_finds_protocol_class(self):
        _write(self.tmp, 'proto.py', '''\
            from typing import Protocol
            class Readable(Protocol):
                def read(self) -> str: ...
        ''')
        structures = collect_structures(self.tmp)
        classes = _extract_all_classes(structures)
        self.assertEqual(classes[0]['name'], 'Readable')
        self.assertIn('Protocol', classes[0]['bases'])

    def test_finds_typeddict(self):
        _write(self.tmp, 'types.py', '''\
            from typing import TypedDict
            class Config(TypedDict):
                name: str
                value: int
        ''')
        structures = collect_structures(self.tmp)
        classes = _extract_all_classes(structures)
        self.assertEqual(classes[0]['name'], 'Config')
        self.assertIn('TypedDict', classes[0]['bases'])

    def test_finds_dataclass(self):
        _write(self.tmp, 'models.py', '''\
            from dataclasses import dataclass
            @dataclass
            class Point:
                x: float
                y: float
        ''')
        structures = collect_structures(self.tmp)
        classes = _extract_all_classes(structures)
        self.assertEqual(classes[0]['name'], 'Point')
        self.assertIn('dataclass', classes[0]['decorators'])

    def test_syntax_error_skipped(self):
        _write(self.tmp, 'bad.py', 'class Broken(\n')
        structures = collect_structures(self.tmp)
        classes = _extract_all_classes(structures)
        self.assertEqual(classes, [])


class TestScanContracts(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_finds_abc(self):
        _write(self.tmp, 'base.py', '''\
            from abc import ABC, abstractmethod
            class MyBase(ABC):
                @abstractmethod
                def do_it(self): ...
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['abcs']), 1)
        self.assertEqual(report['abcs'][0]['name'], 'MyBase')

    def test_finds_protocol(self):
        _write(self.tmp, 'proto.py', '''\
            from typing import Protocol
            class Reader(Protocol):
                def read(self) -> str: ...
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['protocols']), 1)

    def test_finds_typeddict(self):
        _write(self.tmp, 'types.py', '''\
            from typing import TypedDict
            class Config(TypedDict):
                name: str
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['typeddicts']), 1)

    def test_abstract_only_skips_typeddict(self):
        _write(self.tmp, 'types.py', '''\
            from typing import TypedDict, Protocol
            class Config(TypedDict):
                name: str
            class Reader(Protocol):
                def read(self) -> str: ...
        ''')
        report = _scan_contracts(Path(self.tmp), abstract_only=True)
        self.assertEqual(len(report['typeddicts']), 0)
        self.assertEqual(len(report['protocols']), 1)

    def test_implementations_populated(self):
        _write(self.tmp, 'base.py', '''\
            from abc import ABC, abstractmethod
            class Base(ABC):
                @abstractmethod
                def run(self): ...
        ''')
        _write(self.tmp, 'impl.py', '''\
            from base import Base
            class ConcreteImpl(Base):
                def run(self): return 42
        ''')
        report = _scan_contracts(Path(self.tmp))
        abcs = report['abcs']
        self.assertEqual(len(abcs), 1)
        impls = abcs[0]['implementations']
        self.assertEqual(len(impls), 1)
        self.assertEqual(impls[0]['name'], 'ConcreteImpl')

    def test_no_implementations_when_disabled(self):
        _write(self.tmp, 'base.py', '''\
            from abc import ABC, abstractmethod
            class Base(ABC):
                @abstractmethod
                def run(self): ...
        ''')
        _write(self.tmp, 'impl.py', '''\
            class ConcreteImpl(Base):
                def run(self): return 42
        ''')
        report = _scan_contracts(Path(self.tmp), show_implementations=False)
        self.assertEqual(report['abcs'][0]['implementations'], [])

    def test_total_contracts_count(self):
        _write(self.tmp, 'contracts.py', '''\
            from abc import ABC, abstractmethod
            from typing import Protocol, TypedDict
            class MyABC(ABC):
                @abstractmethod
                def x(self): ...
            class MyProto(Protocol):
                def y(self) -> int: ...
            class MyDict(TypedDict):
                z: str
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(report['total_contracts'], 3)

    def test_empty_directory(self):
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(report['total_contracts'], 0)

    def test_finds_protocol_with_generic_subscript(self):
        # BACK-781: class Foo(Protocol[T]) — the subscripted base used to be
        # dropped by the tree-sitter extraction entirely, so the class was
        # invisible to every contract category.
        _write(self.tmp, 'proto.py', '''\
            from typing import Protocol, TypeVar
            T = TypeVar("T")
            class Reader(Protocol[T]):
                def read(self) -> T: ...
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['protocols']), 1)
        self.assertEqual(report['protocols'][0]['name'], 'Reader')

    def test_basemodel_subclass_linked_as_implementation(self):
        # BACK-783: _add_implementations only got abcs+protocols+path_heuristic,
        # so a pydantic BaseModel hierarchy lost its subclass links even though
        # BaseModel is an inheritance-based contract like ABC/Protocol.
        _write(self.tmp, 'models.py', '''\
            from pydantic import BaseModel
            class OkBaseModel(BaseModel):
                x: int
            class IndirectFromBaseModel(OkBaseModel):
                y: int
        ''')
        report = _scan_contracts(Path(self.tmp))
        basemodels = report['basemodels']
        self.assertEqual(len(basemodels), 1)
        impls = basemodels[0]['implementations']
        self.assertEqual(len(impls), 1)
        self.assertEqual(impls[0]['name'], 'IndirectFromBaseModel')

    def test_finds_abc_with_metaclass_kwarg(self):
        # BACK-782: class Foo(metaclass=ABCMeta) — ABCMeta passed as a keyword
        # argument, not a base, so it was invisible to _is_abc. Detection
        # used to depend entirely on the filename matching a path heuristic.
        _write(self.tmp, 'engine.py', '''\
            from abc import ABCMeta
            class Base(metaclass=ABCMeta):
                pass
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['abcs']), 1)
        self.assertEqual(report['abcs'][0]['name'], 'Base')
        self.assertEqual(report['path_heuristic'], [])


class TestRenderReport(unittest.TestCase):

    def _capture(self, report):
        buf = StringIO()
        with patch('sys.stdout', buf):
            _render_report(report)
        return buf.getvalue()

    def _empty_report(self, **kwargs):
        base = {
            'path': '/tmp',
            'total_contracts': 0,
            'abcs': [],
            'protocols': [],
            'typeddicts': [],
            'dataclasses': [],
            'basemodels': [],
            'path_heuristic': [],
        }
        base.update(kwargs)
        return base

    def test_no_contracts_shows_message(self):
        out = self._capture(self._empty_report())
        self.assertIn('No contracts', out)

    def test_coverage_warning_shown_on_false_clean(self):
        # BACK-518: total==0 on a mostly-unsupported tree (stray .py with no
        # contracts) is a false-clean, not a real "no contracts" verdict — the
        # coverage warning fires and replaces the "No contracts or seams" line.
        rep = self._empty_report(coverage={'warning': '⚠ Analyzed 15 of 1,384 '
                                 "source files. Dominant language 'Lua' is not "
                                 'supported by `contracts` — the rest of the '
                                 'tree was not analyzed.'})
        out = self._capture(rep)
        self.assertIn('⚠ Analyzed 15 of 1,384', out)
        self.assertNotIn('No contracts or seams', out)

    def test_coverage_warning_shown_with_results(self):
        abc = {
            'name': 'MyBase', 'file': 'x.py', 'line': 1,
            'bases': ['ABC'], 'abstract_methods': ['run'], 'implementations': [],
        }
        rep = self._empty_report(total_contracts=1, abcs=[abc],
                                 coverage={'warning': '⚠ Analyzed 1 of 900 '
                                 "source files. Dominant language 'Zig' is not "
                                 'supported by `contracts` — the rest of the '
                                 'tree was not analyzed.'})
        out = self._capture(rep)
        self.assertIn('⚠ Analyzed 1 of 900', out)
        self.assertIn('MyBase', out)  # results still shown

    def test_no_warning_when_coverage_clean(self):
        rep = self._empty_report(coverage={'warning': ''})
        out = self._capture(rep)
        self.assertNotIn('⚠', out)
        self.assertIn('No contracts', out)

    def test_shows_path(self):
        out = self._capture(self._empty_report(path='/myproject'))
        self.assertIn('/myproject', out)

    def test_abc_section_shown(self):
        abc = {
            'name': 'MyBase', 'file': 'base.py', 'line': 10,
            'bases': ['ABC'], 'abstract_methods': ['run'],
            'implementations': [],
        }
        report = self._empty_report(total_contracts=1, abcs=[abc])
        out = self._capture(report)
        self.assertIn('Abstract Base Classes', out)
        self.assertIn('MyBase', out)
        self.assertIn('run', out)

    def test_implementations_shown(self):
        abc = {
            'name': 'MyBase', 'file': 'base.py', 'line': 10,
            'bases': ['ABC'], 'abstract_methods': ['run'],
            'implementations': [{'name': 'ConcreteA', 'file': 'impl.py', 'line': 5}],
        }
        report = self._empty_report(total_contracts=1, abcs=[abc])
        out = self._capture(report)
        self.assertIn('ConcreteA', out)
        self.assertIn('implements', out)


class TestRunContracts(unittest.TestCase):

    def test_nonexistent_path_exits_1(self):
        parser = create_contracts_parser()
        args = parser.parse_args(['/nonexistent/path'])
        args.format = 'text'
        with self.assertRaises(SystemExit) as cm:
            run_contracts(args)
        self.assertEqual(cm.exception.code, 1)

    def test_json_format(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, 'base.py', '''\
                from abc import ABC, abstractmethod
                class MyBase(ABC):
                    @abstractmethod
                    def run(self): ...
            ''')
            parser = create_contracts_parser()
            args = parser.parse_args([d])
            args.format = 'json'
            buf = StringIO()
            with patch('sys.stdout', buf):
                run_contracts(args)
            data = json.loads(buf.getvalue())
            self.assertIn('abcs', data)
            self.assertEqual(len(data['abcs']), 1)


class TestScanContractsTypeScript(unittest.TestCase):
    """Tests for TypeScript contract detection."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _write_ts(self, filename: str, content: str) -> str:
        return _write(self.tmp, filename, content)

    def test_interface_classified_as_protocol(self):
        """TypeScript interfaces go into the 'protocols' bucket."""
        self._write_ts('contracts.ts', '''\
            interface IReader {
              read(): string;
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertTrue(report.get('_ts_mode'))
        self.assertEqual(len(report['protocols']), 1)
        self.assertEqual(report['protocols'][0]['name'], 'IReader')

    def test_interface_with_extends_has_bases(self):
        """Interface extends clause populates bases."""
        self._write_ts('contracts.ts', '''\
            interface IBase {
              base(): void;
            }
            interface IDerived extends IBase {
              extra(): void;
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        derived = next(p for p in report['protocols'] if p['name'] == 'IDerived')
        self.assertIn('IBase', derived['bases'])

    def test_abstract_class_classified_as_abc(self):
        """TypeScript abstract classes go into the 'abcs' bucket."""
        self._write_ts('base.ts', '''\
            abstract class AbstractService {
              abstract execute(): void;
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertTrue(report.get('_ts_mode'))
        self.assertEqual(len(report['abcs']), 1)
        self.assertEqual(report['abcs'][0]['name'], 'AbstractService')

    def test_type_alias_classified_as_typeddict(self):
        """TypeScript type aliases go into the 'typeddicts' bucket."""
        self._write_ts('types.ts', '''\
            type Config = {
              host: string;
              port: number;
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['typeddicts']), 1)
        self.assertEqual(report['typeddicts'][0]['name'], 'Config')

    def test_implementing_class_classified_as_dataclass(self):
        """Concrete class with bases goes into 'dataclasses' (implementing classes)."""
        self._write_ts('service.ts', '''\
            interface IService {
              run(): void;
            }
            class ConcreteService implements IService {
              run() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl_names = [c['name'] for c in report['dataclasses']]
        self.assertIn('ConcreteService', impl_names)

    def test_implementations_populated_for_interface(self):
        """Classes implementing an interface appear in that interface's implementations."""
        self._write_ts('service.ts', '''\
            interface IService {
              run(): void;
            }
            class ConcreteService implements IService {
              run() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        iface = next(p for p in report['protocols'] if p['name'] == 'IService')
        impl_names = [i['name'] for i in iface['implementations']]
        self.assertIn('ConcreteService', impl_names)

    def test_implementations_populated_for_abstract_class(self):
        """Classes extending an abstract class appear in its implementations."""
        self._write_ts('base.ts', '''\
            abstract class Base {
              abstract run(): void;
            }
            class Concrete extends Base {
              run() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        abstract = next(a for a in report['abcs'] if a['name'] == 'Base')
        impl_names = [i['name'] for i in abstract['implementations']]
        self.assertIn('Concrete', impl_names)

    def test_abstract_only_skips_type_aliases(self):
        """--abstract-only hides type aliases (typeddicts) and implementing classes."""
        self._write_ts('mixed.ts', '''\
            interface IFoo {
              foo(): void;
            }
            type Bar = { x: number };
            abstract class Baz {
              abstract foo(): void;
            }
        ''')
        report = _scan_contracts(Path(self.tmp), abstract_only=True)
        self.assertEqual(len(report['typeddicts']), 0)
        self.assertEqual(len(report['protocols']), 1)
        self.assertEqual(len(report['abcs']), 1)

    def test_total_contracts_count_ts(self):
        """total_contracts sums interfaces + abstract classes + type aliases."""
        self._write_ts('all.ts', '''\
            interface IFoo { foo(): void; }
            abstract class Bar { abstract bar(): void; }
            type Baz = { x: string };
        ''')
        report = _scan_contracts(Path(self.tmp))
        # 1 interface + 1 abstract class + 1 type alias = 3
        self.assertEqual(report['total_contracts'], 3)

    def test_no_implementations_when_disabled(self):
        """show_implementations=False leaves all implementations lists empty."""
        self._write_ts('service.ts', '''\
            interface IService { run(): void; }
            class ConcreteService implements IService { run() {} }
        ''')
        report = _scan_contracts(Path(self.tmp), show_implementations=False)
        for iface in report['protocols']:
            self.assertEqual(iface['implementations'], [])

    def test_render_uses_ts_labels(self):
        """TypeScript mode renders 'Interfaces' and 'Abstract Classes' labels."""
        self._write_ts('contracts.ts', '''\
            interface IFoo { foo(): void; }
            abstract class Bar { abstract bar(): void; }
        ''')
        report = _scan_contracts(Path(self.tmp))
        buf = StringIO()
        with patch('sys.stdout', buf):
            _render_report(report)
        out = buf.getvalue()
        self.assertIn('Interfaces', out)
        self.assertIn('Abstract Classes', out)
        self.assertNotIn('Abstract Base Classes', out)
        self.assertNotIn('Protocols', out)


class TestScanContractsJavaScript(unittest.TestCase):
    """Tests for plain JS/JSX contract detection (BACK-631).

    JS has no interface/type-alias/abstract-class grammar, so only the
    concrete-class-with-bases path (implementing classes) applies — the
    interface/abstract-class/type-alias cases are TS-only and covered above.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _write_js(self, filename: str, content: str) -> str:
        return _write(self.tmp, filename, content)

    def test_plain_js_reaches_interface_family_scanner(self):
        self._write_js('service.js', '''\
            class Base {
              run() {}
            }
            class Concrete extends Base {
              run() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertTrue(report.get('_ts_mode'))
        impl_names = [c['name'] for c in report['dataclasses']]
        self.assertIn('Concrete', impl_names)
        bases = next(c for c in report['dataclasses'] if c['name'] == 'Concrete')['bases']
        self.assertIn('Base', bases)


class TestScanContractsJava(unittest.TestCase):
    """Tests for Java contract detection (BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _write_java(self, filename: str, content: str) -> str:
        return _write(self.tmp, filename, content)

    def test_interface_classified_as_protocol(self):
        self._write_java('IReader.java', '''\
            public interface IReader {
                String read();
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['protocols']), 1)
        self.assertEqual(report['protocols'][0]['name'], 'IReader')

    def test_interface_with_extends_has_bases(self):
        self._write_java('Interfaces.java', '''\
            public interface IBase {
                void base();
            }
            public interface IDerived extends IBase {
                void extra();
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        derived = next(p for p in report['protocols'] if p['name'] == 'IDerived')
        self.assertIn('IBase', derived['bases'])

    def test_abstract_class_classified_as_abc(self):
        self._write_java('AbstractService.java', '''\
            public abstract class AbstractService {
                abstract void execute();
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['abcs']), 1)
        self.assertEqual(report['abcs'][0]['name'], 'AbstractService')

    def test_implementing_class_classified_as_dataclass(self):
        self._write_java('Service.java', '''\
            interface IService {
                void run();
            }
            class ConcreteService implements IService {
                public void run() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl_names = [c['name'] for c in report['dataclasses']]
        self.assertIn('ConcreteService', impl_names)

    def test_implementations_populated_for_interface(self):
        self._write_java('Service.java', '''\
            interface IService {
                void run();
            }
            class ConcreteService implements IService {
                public void run() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        iface = next(p for p in report['protocols'] if p['name'] == 'IService')
        impl_names = [i['name'] for i in iface['implementations']]
        self.assertIn('ConcreteService', impl_names)

    def test_class_extends_and_implements_both_captured(self):
        self._write_java('Dog.java', '''\
            interface Derived {
                void d();
            }
            class Animal {}
            class Dog extends Animal implements Derived {
                public void d() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl = next(c for c in report['dataclasses'] if c['name'] == 'Dog')
        self.assertIn('Animal', impl['bases'])
        self.assertIn('Derived', impl['bases'])

    def test_plain_class_no_bases_not_a_contract(self):
        """A concrete class with no interface/extends is not a contract."""
        self._write_java('Plain.java', '''\
            public class Plain {
                void doThing() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(report['total_contracts'], 0)

    def test_record_implementing_interface_classified_as_dataclass(self):
        """BACK-810: `record_declaration` (Java 16+ records) is a distinct
        tree-sitter-java node kind, sibling to (not matching)
        `class_declaration` — previously fell through
        `JavaAnalyzer._extract_class_bases`'s dispatch entirely (only
        `class_declaration`/`interface_declaration` were recognized) to the
        base TreeSitterAnalyzer's Python-shaped fallback, always returning
        `[]` for a Java node. A record implementing an interface was
        therefore completely invisible to `contracts`' implementer
        classification (empty bases -> `_classify_ts` never assigns the
        'implementation' category). Confirmed live against samples/java
        (Elasticsearch)."""
        self._write_java('Point.java', '''\
            interface Named {
                String name();
            }
            record Point(int x, int y) implements Named {
                public String name() { return "point"; }
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl = next(c for c in report['dataclasses'] if c['name'] == 'Point')
        self.assertIn('Named', impl['bases'])

    def test_generic_and_qualified_bases_captured(self):
        """BACK-810: a heritage-clause base carrying type arguments parses
        to a `generic_type` node wrapping the real `type_identifier`
        (`extends Bar<Baz>`), and a package/outer-class-qualified base
        parses to a `scoped_type_identifier` (`extends pkg.Bar`) — NEITHER
        wrapper kind matched `_extract_java_class_bases`'s/
        `_extract_java_type_list`'s old bare-`type_identifier`-only check,
        so any generic or qualified base name was silently dropped from
        `bases` entirely. Not a rare shape: it's the dominant idiom for a
        typed abstract-base/generic-interface implementer
        (`extends AbstractIndexAnalyzerProvider<ArabicAnalyzer>`,
        `implements ActionListener<Response>`) — confirmed to account for
        the large majority (517/2527) of `contracts` implementer false
        negatives measured against samples/java (Elasticsearch)."""
        self._write_java('Generic.java', '''\
            interface ActionListener<T> {
                void onResponse(T response);
            }
            abstract class AbstractProvider<T> implements ActionListener<T> {
            }
            class ConcreteProvider extends AbstractProvider<String> implements Comparable<String> {
                public void onResponse(String response) {}
                public int compareTo(String o) { return 0; }
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        abstract_provider = next(c for c in report['abcs'] if c['name'] == 'AbstractProvider')
        self.assertIn('ActionListener', abstract_provider['bases'])
        concrete = next(c for c in report['dataclasses'] if c['name'] == 'ConcreteProvider')
        self.assertIn('AbstractProvider', concrete['bases'])
        self.assertIn('Comparable', concrete['bases'])

    def test_qualified_superclass_base_captured(self):
        """BACK-810: a package-qualified `extends` base (`extends pkg.Bar`,
        no generics) parses to a `scoped_type_identifier` — the base's own
        simple name is the RIGHTMOST `type_identifier` child of the
        (possibly left-recursively nested) scoped identifier."""
        self._write_java('Qualified.java', '''\
            package app;
            abstract class Base {
                abstract void run();
            }
            class Impl extends app.Base {
                void run() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl = next(c for c in report['dataclasses'] if c['name'] == 'Impl')
        self.assertIn('Base', impl['bases'])


class TestScanContractsCSharp(unittest.TestCase):
    """Tests for C# contract detection (BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _write_cs(self, filename: str, content: str) -> str:
        return _write(self.tmp, filename, content)

    def test_interface_classified_as_protocol(self):
        self._write_cs('IReader.cs', '''\
            public interface IReader {
                string Read();
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['protocols']), 1)
        self.assertEqual(report['protocols'][0]['name'], 'IReader')

    def test_interface_with_extends_has_bases(self):
        self._write_cs('Interfaces.cs', '''\
            public interface IBase {
                void Base();
            }
            public interface IDerived : IBase {
                void Extra();
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        derived = next(p for p in report['protocols'] if p['name'] == 'IDerived')
        self.assertIn('IBase', derived['bases'])

    def test_abstract_class_classified_as_abc(self):
        self._write_cs('AbstractService.cs', '''\
            public abstract class AbstractService {
                public abstract void Execute();
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['abcs']), 1)
        self.assertEqual(report['abcs'][0]['name'], 'AbstractService')

    def test_implementing_class_classified_as_dataclass(self):
        self._write_cs('Service.cs', '''\
            interface IService {
                void Run();
            }
            class ConcreteService : IService {
                public void Run() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl_names = [c['name'] for c in report['dataclasses']]
        self.assertIn('ConcreteService', impl_names)

    def test_class_extends_and_implements_both_captured(self):
        self._write_cs('Dog.cs', '''\
            interface IDerived {
                void D();
            }
            class Animal {}
            class Dog : Animal, IDerived {
                public void D() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl = next(c for c in report['dataclasses'] if c['name'] == 'Dog')
        self.assertIn('Animal', impl['bases'])
        self.assertIn('IDerived', impl['bases'])

    def test_plain_class_no_bases_not_a_contract(self):
        self._write_cs('Plain.cs', '''\
            public class Plain {
                void DoThing() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(report['total_contracts'], 0)

    def test_qualified_namespace_base_still_captured(self):
        """BACK-797: `class Foo : Ns.Sub.IBar` — a namespace-qualified base
        parses to a `qualified_name` node, distinct from bare `identifier`,
        that `_csharp_base_item_name` used to fall through and drop
        entirely. Confirmed live on samples/csharp (Jellyfin):
        `BaseVideoResolver<T> : MediaBrowser.Controller.Resolvers.
        ItemResolver<T>` lost its only base, hiding a real abstract-class
        implementer relationship."""
        self._write_cs('Qualified.cs', '''\
            namespace Ns.Sub {
                public abstract class Base {
                    public abstract void Do();
                }
            }
            class Foo : Ns.Sub.Base {
                public override void Do() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl = next(c for c in report['dataclasses'] if c['name'] == 'Foo')
        self.assertIn('Base', impl['bases'])

    def test_record_implementing_interface_classified_as_dataclass(self):
        """BACK-797: `record_declaration` is a distinct tree-sitter-c-sharp
        node kind from `class_declaration`/`struct_declaration` — it was
        entirely absent from CLASS_NODE_TYPES before this fix, so a record
        implementing an interface (a common C# 9+ DTO idiom) was invisible
        to get_structure()'s classes extraction and never appeared as an
        implementer here. Confirmed live on samples/csharp (Jellyfin)."""
        self._write_cs('PointRec.cs', '''\
            interface IPoint {
                int X { get; }
            }
            public record PointRec(int X, int Y) : IPoint;
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl_names = [c['name'] for c in report['dataclasses']]
        self.assertIn('PointRec', impl_names)
        impl = next(c for c in report['dataclasses'] if c['name'] == 'PointRec')
        self.assertIn('IPoint', impl['bases'])


class TestScanContractsPhp(unittest.TestCase):
    """Tests for PHP contract detection (BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _write_php(self, filename: str, content: str) -> str:
        return _write(self.tmp, filename, content)

    def test_interface_classified_as_protocol(self):
        self._write_php('Reader.php', '''\
            <?php
            interface Reader {
                public function read(): string;
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['protocols']), 1)
        self.assertEqual(report['protocols'][0]['name'], 'Reader')

    def test_interface_with_extends_has_bases(self):
        self._write_php('Interfaces.php', '''\
            <?php
            interface Base {
                public function base(): void;
            }
            interface Derived extends Base {
                public function extra(): void;
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        derived = next(p for p in report['protocols'] if p['name'] == 'Derived')
        self.assertIn('Base', derived['bases'])

    def test_abstract_class_classified_as_abc(self):
        self._write_php('AbstractService.php', '''\
            <?php
            abstract class AbstractService {
                abstract public function execute(): void;
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['abcs']), 1)
        self.assertEqual(report['abcs'][0]['name'], 'AbstractService')

    def test_implementing_class_classified_as_dataclass(self):
        self._write_php('Service.php', '''\
            <?php
            interface Service {
                public function run(): void;
            }
            class ConcreteService implements Service {
                public function run(): void {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl_names = [c['name'] for c in report['dataclasses']]
        self.assertIn('ConcreteService', impl_names)

    def test_implementations_populated_for_interface(self):
        self._write_php('Service.php', '''\
            <?php
            interface Service {
                public function run(): void;
            }
            class ConcreteService implements Service {
                public function run(): void {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        iface = next(p for p in report['protocols'] if p['name'] == 'Service')
        impl_names = [i['name'] for i in iface['implementations']]
        self.assertIn('ConcreteService', impl_names)

    def test_class_extends_and_implements_both_captured(self):
        self._write_php('Dog.php', '''\
            <?php
            interface Derived {
                public function d(): void;
            }
            class Animal {}
            class Dog extends Animal implements Derived {
                public function d(): void {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl = next(c for c in report['dataclasses'] if c['name'] == 'Dog')
        self.assertIn('Animal', impl['bases'])
        self.assertIn('Derived', impl['bases'])

    def test_plain_class_no_bases_not_a_contract(self):
        self._write_php('Plain.php', '''\
            <?php
            class Plain {
                public function doThing(): void {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(report['total_contracts'], 0)


class TestScanContractsSwift(unittest.TestCase):
    """Tests for Swift contract detection (BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _write_swift(self, filename: str, content: str) -> str:
        return _write(self.tmp, filename, content)

    def test_protocol_classified_as_protocol(self):
        self._write_swift('Reader.swift', '''\
            protocol Reader {
                func read() -> String
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['protocols']), 1)
        self.assertEqual(report['protocols'][0]['name'], 'Reader')

    def test_protocol_with_inheritance_has_bases(self):
        self._write_swift('Protocols.swift', '''\
            protocol Base {
                func base()
            }
            protocol Derived: Base {
                func extra()
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        derived = next(p for p in report['protocols'] if p['name'] == 'Derived')
        self.assertIn('Base', derived['bases'])

    def test_conforming_class_classified_as_implementation(self):
        self._write_swift('Service.swift', '''\
            protocol Service {
                func run()
            }
            class ConcreteService: Service {
                func run() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl_names = [c['name'] for c in report['dataclasses']]
        self.assertIn('ConcreteService', impl_names)

    def test_implementations_populated_for_protocol(self):
        self._write_swift('Service.swift', '''\
            protocol Service {
                func run()
            }
            class ConcreteService: Service {
                func run() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        iface = next(p for p in report['protocols'] if p['name'] == 'Service')
        impl_names = [i['name'] for i in iface['implementations']]
        self.assertIn('ConcreteService', impl_names)

    def test_class_multiple_conformances_captured(self):
        self._write_swift('Circle.swift', '''\
            protocol Drawable { func draw() }
            class Base {}
            class Circle: Base, Drawable {
                func draw() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl = next(c for c in report['dataclasses'] if c['name'] == 'Circle')
        self.assertIn('Base', impl['bases'])
        self.assertIn('Drawable', impl['bases'])

    def test_plain_class_no_bases_not_a_contract(self):
        self._write_swift('Plain.swift', '''\
            class Plain {
                func doThing() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(report['total_contracts'], 0)


class TestScanContractsKotlin(unittest.TestCase):
    """Tests for Kotlin contract detection (BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _write_kt(self, filename: str, content: str) -> str:
        return _write(self.tmp, filename, content)

    def test_interface_classified_as_protocol(self):
        self._write_kt('Reader.kt', '''\
            interface Reader {
                fun read(): String
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['protocols']), 1)
        self.assertEqual(report['protocols'][0]['name'], 'Reader')

    def test_interface_with_inheritance_has_bases(self):
        self._write_kt('Interfaces.kt', '''\
            interface Base {
                fun base()
            }
            interface Derived : Base {
                fun extra()
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        derived = next(p for p in report['protocols'] if p['name'] == 'Derived')
        self.assertIn('Base', derived['bases'])

    def test_abstract_class_classified_as_abc(self):
        self._write_kt('AbstractService.kt', '''\
            abstract class AbstractService {
                abstract fun execute()
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['abcs']), 1)
        self.assertEqual(report['abcs'][0]['name'], 'AbstractService')

    def test_interface_not_miscounted_as_implementation(self):
        """A Kotlin interface parses as class_declaration; it must be
        repartitioned into 'interfaces', not left in the implementing bucket."""
        self._write_kt('Shapes.kt', '''\
            interface Shape { fun area(): Double }
            interface Drawable : Shape { fun draw() }
        ''')
        report = _scan_contracts(Path(self.tmp))
        proto_names = {p['name'] for p in report['protocols']}
        impl_names = {c['name'] for c in report['dataclasses']}
        self.assertIn('Drawable', proto_names)
        self.assertNotIn('Drawable', impl_names)

    def test_implementing_class_classified_as_dataclass(self):
        self._write_kt('Service.kt', '''\
            interface Service {
                fun run()
            }
            class ConcreteService : Service {
                override fun run() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl_names = [c['name'] for c in report['dataclasses']]
        self.assertIn('ConcreteService', impl_names)

    def test_implementations_populated_for_interface(self):
        self._write_kt('Service.kt', '''\
            interface Service {
                fun run()
            }
            class ConcreteService : Service {
                override fun run() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        iface = next(p for p in report['protocols'] if p['name'] == 'Service')
        impl_names = [i['name'] for i in iface['implementations']]
        self.assertIn('ConcreteService', impl_names)

    def test_class_extends_and_implements_both_captured(self):
        self._write_kt('Circle.kt', '''\
            interface Drawable { fun draw() }
            open class Base
            class Circle : Base(), Drawable {
                override fun draw() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl = next(c for c in report['dataclasses'] if c['name'] == 'Circle')
        self.assertIn('Base', impl['bases'])
        self.assertIn('Drawable', impl['bases'])

    def test_plain_class_no_bases_not_a_contract(self):
        self._write_kt('Plain.kt', '''\
            class Plain {
                fun doThing() {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(report['total_contracts'], 0)


class TestScanContractsRuby(unittest.TestCase):
    """Tests for Ruby contract detection — the mixin model (BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _write_rb(self, filename: str, content: str) -> str:
        return _write(self.tmp, filename, content)

    def test_module_classified_as_protocol(self):
        self._write_rb('greetable.rb', '''\
            module Greetable
              def greet
                "hi"
              end
            end
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(len(report['protocols']), 1)
        self.assertEqual(report['protocols'][0]['name'], 'Greetable')

    def test_including_class_classified_as_dataclass(self):
        self._write_rb('user.rb', '''\
            module Greetable
              def greet
                "hi"
              end
            end

            class User
              include Greetable
            end
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl_names = [c['name'] for c in report['dataclasses']]
        self.assertIn('User', impl_names)

    def test_implementations_populated_for_module(self):
        self._write_rb('user.rb', '''\
            module Greetable
              def greet
                "hi"
              end
            end

            class User
              include Greetable
            end
        ''')
        report = _scan_contracts(Path(self.tmp))
        mod = next(p for p in report['protocols'] if p['name'] == 'Greetable')
        impl_names = [i['name'] for i in mod['implementations']]
        self.assertIn('User', impl_names)

    def test_extend_also_counts_as_implementation(self):
        self._write_rb('trackable.rb', '''\
            module Trackable
            end

            class Widget
              extend Trackable
            end
        ''')
        report = _scan_contracts(Path(self.tmp))
        mod = next(p for p in report['protocols'] if p['name'] == 'Trackable')
        impl_names = [i['name'] for i in mod['implementations']]
        self.assertIn('Widget', impl_names)

    def test_prepend_also_counts_as_implementation(self):
        """BACK-809: `prepend` (Ruby's third mixin mechanism, alongside
        `include`/`extend`) was invisible to `_mixin_names` -- confirmed via
        the BACK-808 Ruby recall-oracle slice against
        samples/ruby/lib/freedom_patches/rspec_mocks_from_described_class.rb
        (`class MethodDouble; prepend MethodDoubleExtensions; end`)."""
        self._write_rb('wrappable.rb', '''\
            module Wrappable
            end

            class MethodDouble
              prepend Wrappable
            end
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl_names = [c['name'] for c in report['dataclasses']]
        self.assertIn('MethodDouble', impl_names)
        mod = next(p for p in report['protocols'] if p['name'] == 'Wrappable')
        mod_impl_names = [i['name'] for i in mod['implementations']]
        self.assertIn('MethodDouble', mod_impl_names)

    def test_superclass_and_mixin_both_captured(self):
        self._write_rb('animal.rb', '''\
            module Derived
            end

            class Animal
            end

            class Dog < Animal
              include Derived
            end
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl = next(c for c in report['dataclasses'] if c['name'] == 'Dog')
        self.assertIn('Animal', impl['bases'])
        self.assertIn('Derived', impl['bases'])

    def test_namespaced_include_resolves_to_tail_name(self):
        self._write_rb('concern.rb', '''\
            module MyApp
              module Greetable
              end
            end

            class User
              include MyApp::Greetable
            end
        ''')
        report = _scan_contracts(Path(self.tmp))
        mod = next(p for p in report['protocols'] if p['name'] == 'Greetable')
        impl_names = [i['name'] for i in mod['implementations']]
        self.assertIn('User', impl_names)

    def test_plain_class_no_bases_not_a_contract(self):
        self._write_rb('plain.rb', '''\
            class Plain
              def do_thing
              end
            end
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(report['total_contracts'], 0)
        self.assertEqual(len(report['dataclasses']), 0)

    def test_plain_superclass_no_module_not_a_contract(self):
        self._write_rb('application_record.rb', '''\
            class ApplicationRecord
            end

            class User < ApplicationRecord
            end
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(report['total_contracts'], 0)

    def test_include_inside_method_body_not_counted(self):
        self._write_rb('dynamic.rb', '''\
            module Greetable
            end

            class User
              def self.enable_greeting
                include Greetable
              end
            end
        ''')
        report = _scan_contracts(Path(self.tmp))
        impl_names = [c['name'] for c in report['dataclasses']]
        self.assertNotIn('User', impl_names)


class TestScanContractsGo(unittest.TestCase):
    """Tests for Go contract detection — interfaces + structural implementers
    (BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _write_go(self, filename: str, content: str) -> str:
        return _write(self.tmp, filename, content)

    def test_interface_classified_as_protocol(self):
        self._write_go('store.go', '''\
            package storage
            type Store interface {
            \tGet(key string) ([]byte, error)
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertTrue(report.get('_go_mode'))
        self.assertEqual([p['name'] for p in report['protocols']], ['Store'])

    def test_struct_with_all_methods_implements_interface(self):
        self._write_go('store.go', '''\
            package storage
            type Store interface {
            \tGet(key string) ([]byte, error)
            \tPut(key string, val []byte) error
            }
            type MemStore struct{}
            func (m *MemStore) Get(key string) ([]byte, error) { return nil, nil }
            func (m *MemStore) Put(key string, val []byte) error { return nil }
        ''')
        report = _scan_contracts(Path(self.tmp))
        store = next(p for p in report['protocols'] if p['name'] == 'Store')
        self.assertIn('MemStore', [i['name'] for i in store['implementations']])
        self.assertIn('MemStore', [c['name'] for c in report['dataclasses']])

    def test_struct_missing_a_method_does_not_implement(self):
        """Superset match: a struct missing any interface method is not an
        implementer (the trust-preserving direction — no false 'implements')."""
        self._write_go('store.go', '''\
            package storage
            type Store interface {
            \tGet(key string) ([]byte, error)
            \tPut(key string, val []byte) error
            }
            type WriteOnly struct{}
            func (w *WriteOnly) Put(key string, val []byte) error { return nil }
        ''')
        report = _scan_contracts(Path(self.tmp))
        store = next(p for p in report['protocols'] if p['name'] == 'Store')
        self.assertEqual(store['implementations'], [])

    def test_embedded_interface_methods_resolved_transitively(self):
        self._write_go('store.go', '''\
            package storage
            type Reader interface {
            \tRead() ([]byte, error)
            }
            type ReadStore interface {
            \tReader
            \tWrite() error
            }
            type File struct{}
            func (f *File) Read() ([]byte, error) { return nil, nil }
            func (f *File) Write() error { return nil }
        ''')
        report = _scan_contracts(Path(self.tmp))
        rs = next(p for p in report['protocols'] if p['name'] == 'ReadStore')
        self.assertIn('File', [i['name'] for i in rs['implementations']])

    def test_empty_marker_interface_has_no_implementers(self):
        """`interface{}` (0 methods) is surfaced as a contract but must not
        match every type — an empty required-set would trivially include all."""
        self._write_go('marker.go', '''\
            package storage
            type Marker interface{}
            type Thing struct{}
            func (t *Thing) Do() {}
        ''')
        report = _scan_contracts(Path(self.tmp))
        marker = next(p for p in report['protocols'] if p['name'] == 'Marker')
        self.assertEqual(marker['implementations'], [])
        self.assertEqual(report['dataclasses'], [])

    def test_value_receiver_methods_count(self):
        """A value receiver (`func (m T)`) contributes to the method set the
        same as a pointer receiver."""
        self._write_go('store.go', '''\
            package storage
            type Doer interface {
            \tDo() error
            }
            type Worker struct{}
            func (w Worker) Do() error { return nil }
        ''')
        report = _scan_contracts(Path(self.tmp))
        doer = next(p for p in report['protocols'] if p['name'] == 'Doer')
        self.assertIn('Worker', [i['name'] for i in doer['implementations']])

    def test_same_method_name_different_return_type_is_not_an_implementer(self):
        """BACK-816: name-only matching let a struct method with the same
        name but an incompatible return type falsely satisfy an interface
        (the ObserverVec/*Vec shape from client_golang) — `With(l Labels)
        Observer` is not satisfied by `With(l Labels) *Gauge`."""
        self._write_go('vec.go', '''\
            package prometheus
            type Observer interface {
            \tObserve(v float64)
            }
            type ObserverVec interface {
            \tWith(l Labels) Observer
            }
            type GaugeVec struct{}
            func (v *GaugeVec) With(l Labels) *Gauge { return nil }
        ''')
        report = _scan_contracts(Path(self.tmp))
        ov = next(p for p in report['protocols'] if p['name'] == 'ObserverVec')
        self.assertEqual(ov['implementations'], [])
        self.assertEqual(report['dataclasses'], [])

    def test_same_method_name_different_param_type_is_not_an_implementer(self):
        """BACK-816: same principle on the parameter side — `With(l Labels)`
        is not satisfied by a method named `With` that takes a different
        parameter type."""
        self._write_go('vec.go', '''\
            package prometheus
            type Setter interface {
            \tWith(l Labels) error
            }
            type Other struct{}
            func (o *Other) With(n int) error { return nil }
        ''')
        report = _scan_contracts(Path(self.tmp))
        setter = next(p for p in report['protocols'] if p['name'] == 'Setter')
        self.assertEqual(setter['implementations'], [])

    def test_go_abstract_only_omits_implementers(self):
        self._write_go('store.go', '''\
            package storage
            type Store interface {
            \tGet() error
            }
            type MemStore struct{}
            func (m *MemStore) Get() error { return nil }
        ''')
        report = _scan_contracts(Path(self.tmp), abstract_only=True)
        self.assertEqual(report['dataclasses'], [])
        self.assertEqual([p['name'] for p in report['protocols']], ['Store'])


class TestScanContractsRust(unittest.TestCase):
    """Tests for Rust contract detection — traits + explicit impls (BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _write_rs(self, filename: str, content: str) -> str:
        return _write(self.tmp, filename, content)

    def test_trait_classified_as_protocol(self):
        self._write_rs('store.rs', '''\
            trait Store {
                fn get(&self) -> Vec<u8>;
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertTrue(report.get('_rust_mode'))
        self.assertEqual([p['name'] for p in report['protocols']], ['Store'])

    def test_impl_for_records_implementation(self):
        self._write_rs('store.rs', '''\
            trait Store {
                fn get(&self) -> Vec<u8>;
            }
            struct MemStore;
            impl Store for MemStore {
                fn get(&self) -> Vec<u8> { vec![] }
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        store = next(p for p in report['protocols'] if p['name'] == 'Store')
        self.assertIn('MemStore', [i['name'] for i in store['implementations']])
        self.assertIn('MemStore', [c['name'] for c in report['dataclasses']])

    def test_inherent_impl_not_an_implementation(self):
        """`impl Type {}` (no `for`) is an inherent impl, not a trait
        implementation — it must not appear as an implementer."""
        self._write_rs('store.rs', '''\
            trait Store {
                fn get(&self);
            }
            struct MemStore;
            impl MemStore {
                fn helper(&self) {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        store = next(p for p in report['protocols'] if p['name'] == 'Store')
        self.assertEqual(store['implementations'], [])
        self.assertEqual(report['dataclasses'], [])

    def test_type_implementing_multiple_traits(self):
        self._write_rs('store.rs', '''\
            trait Reader { fn read(&self); }
            trait Writer { fn write(&self); }
            struct File;
            impl Reader for File { fn read(&self) {} }
            impl Writer for File { fn write(&self) {} }
        ''')
        report = _scan_contracts(Path(self.tmp))
        file_impl = next(c for c in report['dataclasses'] if c['name'] == 'File')
        self.assertEqual(file_impl['bases'], ['Reader', 'Writer'])

    def test_generic_impl_target_resolves_base_type(self):
        """`impl Trait for Type<T>` records the base type name, not the
        generic wrapper."""
        self._write_rs('store.rs', '''\
            trait Store { fn get(&self); }
            struct Cache<T> { inner: T }
            impl<T> Store for Cache<T> {
                fn get(&self) {}
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        store = next(p for p in report['protocols'] if p['name'] == 'Store')
        self.assertIn('Cache', [i['name'] for i in store['implementations']])

    def test_rust_abstract_only_omits_implementers(self):
        self._write_rs('store.rs', '''\
            trait Store { fn get(&self); }
            struct MemStore;
            impl Store for MemStore { fn get(&self) {} }
        ''')
        report = _scan_contracts(Path(self.tmp), abstract_only=True)
        self.assertEqual(report['dataclasses'], [])
        self.assertEqual([p['name'] for p in report['protocols']], ['Store'])

    def test_same_named_type_in_different_files_not_conflated(self):
        """BACK-794: a short/generic type name (e.g. `Error`) reused for
        unrelated types across files must not collapse into one bogus
        implementer entry with a unioned `bases` list — each file's type
        gets its own implementer row."""
        self._write_rs('a/error.rs', '''\
            trait ErrorCode { fn code(&self); }
            struct Error;
            impl ErrorCode for Error { fn code(&self) {} }
        ''')
        self._write_rs('b/error.rs', '''\
            trait Display { fn fmt(&self); }
            struct Error;
            impl Display for Error { fn fmt(&self) {} }
        ''')
        report = _scan_contracts(Path(self.tmp))
        error_impls = [c for c in report['dataclasses'] if c['name'] == 'Error']
        self.assertEqual(len(error_impls), 2)
        files = {Path(c['file']).parent.name: c['bases'] for c in error_impls}
        self.assertEqual(files['a'], ['ErrorCode'])
        self.assertEqual(files['b'], ['Display'])


class TestScanContractsCpp(unittest.TestCase):
    """Tests for C++ contract detection — abstract classes + subclasses
    (BACK-403 pt 2)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _write_cpp(self, filename: str, content: str) -> str:
        return _write(self.tmp, filename, content)

    def test_abstract_class_classified_as_contract(self):
        self._write_cpp('store.cpp', '''\
            class Store {
            public:
                virtual int get() = 0;
            };
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertTrue(report.get('_cpp_mode'))
        self.assertEqual([p['name'] for p in report['protocols']], ['Store'])

    def test_non_abstract_class_not_a_contract(self):
        """A class with only concrete methods is not a contract."""
        self._write_cpp('plain.cpp', '''\
            class Widget {
            public:
                int compute() { return 1; }
            };
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(report['total_contracts'], 0)

    def test_subclass_recorded_as_implementation(self):
        self._write_cpp('store.cpp', '''\
            class Store {
            public:
                virtual int get() = 0;
            };
            class MemStore : public Store {
            public:
                int get() override { return 1; }
            };
        ''')
        report = _scan_contracts(Path(self.tmp))
        store = next(p for p in report['protocols'] if p['name'] == 'Store')
        self.assertIn('MemStore', [i['name'] for i in store['implementations']])
        self.assertIn('MemStore', [c['name'] for c in report['dataclasses']])

    def test_multiple_inheritance_bases(self):
        self._write_cpp('m.cpp', '''\
            class Reader { public: virtual int read() = 0; };
            class Writer { public: virtual void write() = 0; };
            class File : public Reader, public Writer {
            public:
                int read() override { return 0; }
                void write() override {}
            };
        ''')
        report = _scan_contracts(Path(self.tmp))
        file_impl = next(c for c in report['dataclasses'] if c['name'] == 'File')
        self.assertEqual(file_impl['bases'], ['Reader', 'Writer'])

    def test_cpp_abstract_only_omits_subclasses(self):
        self._write_cpp('store.cpp', '''\
            class Store { public: virtual int get() = 0; };
            class MemStore : public Store { public: int get() override { return 1; } };
        ''')
        report = _scan_contracts(Path(self.tmp), abstract_only=True)
        self.assertEqual(report['dataclasses'], [])
        self.assertEqual([p['name'] for p in report['protocols']], ['Store'])

    def test_header_only_abstract_class_classified_as_contract(self):
        """BACK-630: a .h with no sibling .cpp (Godot-style) must not be invisible."""
        self._write_cpp('store.h', '''\
            class Store {
            public:
                virtual int get() = 0;
            };
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertTrue(report.get('_cpp_mode'))
        self.assertEqual([p['name'] for p in report['protocols']], ['Store'])

    def test_plain_c_header_not_treated_as_cpp(self):
        """A genuine C header (no C++-only markers) must not enter cpp mode."""
        self._write_cpp('widget.h', '''\
            struct Widget {
                int value;
            };
            int widget_compute(struct Widget *w);
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertFalse(report.get('_cpp_mode'))

    def test_macro_prefixed_abstract_class_not_dropped(self):
        """BACK-796 (BACK-795 measurement): a DLL-export/visibility macro
        between `class`/`struct` and the real class name (`class ASSIMP_API
        BaseProcess { ... }` — Assimp's own convention, also Qt's
        `Q_CORE_EXPORT`, wxWidgets' `WXDLLIMPEXP_CORE`, etc) used to make the
        class invisible entirely: tree-sitter-cpp has no grammar rule for two
        bare identifiers in a row after `class`/`struct`, so it produced a
        bodyless, wrong-named `class_specifier` (named after the macro) and
        absorbed the real body elsewhere in the tree. Confirmed against
        Assimp's real `BaseProcess` (2 pure-virtual methods) during the
        BACK-795 C++ recall-oracle measurement.
        """
        self._write_cpp('base_process.h', '''\
            class ASSIMP_API BaseProcess {
            public:
                virtual bool IsActive(unsigned int flags) const = 0;
                virtual void Execute(int scene) = 0;
            };
            class ASSIMP_API_WINONLY ConcreteProcess final : public BaseProcess {
            public:
                bool IsActive(unsigned int flags) const override { return true; }
                void Execute(int scene) override {}
            };
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertTrue(report.get('_cpp_mode'))
        names = [p['name'] for p in report['protocols']]
        self.assertIn('BaseProcess', names)
        base = next(p for p in report['protocols'] if p['name'] == 'BaseProcess')
        self.assertTrue(base['is_abstract'])
        self.assertIn('ConcreteProcess', [c['name'] for c in report['dataclasses']])

    def test_elaborated_type_specifier_declaration_not_corrupted(self):
        """A C-compatibility elaborated-type-specifier variable declaration
        (`struct stat st;` / `class Point p;`) also has two bare identifiers
        back-to-back after the keyword, but ends the statement in `;` — not
        `{`/`:` — so it must NOT be treated as a macro-prefixed class
        definition (that would wrongly blank a real type name). Point's own
        definition carries a pure virtual so the fix's blanking (if wrongly
        triggered on the later `struct Point p;` reference) would be
        detectable via a corrupted/duplicated contract name.
        """
        self._write_cpp('legacy.cpp', '''\
            struct Point { public: virtual int norm() = 0; };
            void f() {
                struct Point p;
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual([p['name'] for p in report['protocols']], ['Point'])

    def test_final_specifier_subclass_not_renamed(self):
        """Regression (found alongside BACK-796): `class MemStore final :
        public Store { ... }` must still resolve to the real class name
        `MemStore`, not `final`."""
        self._write_cpp('store.cpp', '''\
            class Store {
            public:
                virtual int get() = 0;
            };
            class MemStore final : public Store {
            public:
                int get() override { return 1; }
            };
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertIn('MemStore', [c['name'] for c in report['dataclasses']])
        self.assertNotIn('final', [c['name'] for c in report['dataclasses']])


class TestNormalizeCppMacroClassModifiers(unittest.TestCase):
    """Direct unit tests for BACK-796's fix
    (`normalize_cpp_macro_class_modifiers`, `nav_surface_common.py`)."""

    def _norm(self, source: str) -> str:
        from reveal.adapters.ast.nav_surface_common import normalize_cpp_macro_class_modifiers
        return normalize_cpp_macro_class_modifiers(source)

    def test_blanks_macro_before_class_definition(self):
        out = self._norm('class ASSIMP_API BaseProcess {\n};\n')
        self.assertNotIn('ASSIMP_API', out)
        self.assertIn('BaseProcess', out)
        # Length and line count preserved (byte offsets stay valid).
        self.assertEqual(len(out), len('class ASSIMP_API BaseProcess {\n};\n'))

    def test_blanks_macro_before_inheritance_list(self):
        out = self._norm('class ASSIMP_API_WINONLY Foo final : public Base {\n};\n')
        self.assertNotIn('ASSIMP_API_WINONLY', out)
        self.assertIn('Foo final : public Base', out)

    def test_leaves_ordinary_class_untouched(self):
        src = 'class Widget {\npublic:\n    int compute();\n};\n'
        self.assertEqual(self._norm(src), src)

    def test_leaves_elaborated_type_specifier_untouched(self):
        """`struct Point p;` ends in `;`, not `{`/`:` — must not be blanked."""
        src = 'struct Point p;\n'
        self.assertEqual(self._norm(src), src)

    def test_leaves_forward_declaration_untouched(self):
        src = 'class Foo;\n'
        self.assertEqual(self._norm(src), src)

    def test_leaves_final_specifier_class_untouched(self):
        """Regression: `class Name final : public Base {` also has two bare
        identifiers in a row (`Name`, `final`) — but `final` is the
        trailing specifier, not a second real identifier, so `Name` (the
        real class name) must NOT be blanked. Caught during the BACK-795
        measurement session against Godot's own
        `JoltCustomRayShapeSupport final : ...` — the fix's first draft
        blanked the real class name and kept `final` as if it were the
        class."""
        src = 'class JoltCustomRayShapeSupport final : public Base {\n};\n'
        self.assertEqual(self._norm(src), src)

    def test_blanks_macro_with_preprocessor_conditional_before_colon(self):
        """`class ASSIMP_API Name\\n#ifndef SWIG\\n    : public Base\\n#endif\\n{`
        — Assimp's own `IOStream.hpp`/`IOSystem.hpp`/`Logger.hpp`/etc (5
        files) guard the base-class clause behind a SWIG-binding
        preprocessor conditional, putting `#ifndef`/`#endif` lines between
        the class name and the `:`/`{` the lookahead checks for. The
        lookahead must skip preprocessor-directive lines (not just
        whitespace) to still recognize this as a genuine definition."""
        out = self._norm(
            'class ASSIMP_API IOStream\n'
            '#ifndef SWIG\n'
            '    : public Base\n'
            '#endif\n'
            '{\n};\n'
        )
        self.assertNotIn('ASSIMP_API', out)
        self.assertIn('IOStream', out)

    def test_blanks_macro_before_final_specifier_class(self):
        """`class MACRO Name final : public Base {` — three bare tokens —
        must still blank only the macro, keeping both `Name` and `final`."""
        out = self._norm('class ASSIMP_API_WINONLY Foo final : public Base {\n};\n')
        self.assertNotIn('ASSIMP_API_WINONLY', out)
        self.assertIn('Foo final : public Base', out)


class TestScanContractsPolyglot(unittest.TestCase):
    """BACK-780: a repo with more than one contract-bearing language must not
    silently drop every non-winning language's contracts."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _write(self, filename: str, content: str) -> str:
        return _write(self.tmp, filename, content)

    def test_python_and_go_both_reported(self):
        self._write('svc.py', '''\
            from abc import ABC, abstractmethod
            class PyContract(ABC):
                @abstractmethod
                def run(self): ...
        ''')
        self._write('svc.go', '''\
            package svc
            type GoContract interface {
            \tRun() error
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertNotIn('abcs', report)  # flat single-language shape must not leak through
        by_language = report['by_language']
        self.assertEqual(report['total_contracts'], 2)
        self.assertEqual([a['name'] for a in by_language['python']['abcs']], ['PyContract'])
        self.assertEqual([p['name'] for p in by_language['go']['protocols']], ['GoContract'])

    def test_coverage_reflects_both_languages_present(self):
        self._write('svc.py', '''\
            from abc import ABC, abstractmethod
            class PyContract(ABC):
                @abstractmethod
                def run(self): ...
        ''')
        self._write('svc.go', '''\
            package svc
            type GoContract interface {
            \tRun() error
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertEqual(report['coverage']['analyzed_files'], 2)

    def test_single_language_shape_unaffected(self):
        """A pure-Python repo must keep the flat (non-`by_language`) shape."""
        self._write('svc.py', '''\
            from abc import ABC, abstractmethod
            class PyContract(ABC):
                @abstractmethod
                def run(self): ...
        ''')
        report = _scan_contracts(Path(self.tmp))
        self.assertNotIn('by_language', report)
        self.assertEqual([a['name'] for a in report['abcs']], ['PyContract'])

    def test_render_report_shows_both_languages(self):
        self._write('svc.py', '''\
            from abc import ABC, abstractmethod
            class PyContract(ABC):
                @abstractmethod
                def run(self): ...
        ''')
        self._write('svc.go', '''\
            package svc
            type GoContract interface {
            \tRun() error
            }
        ''')
        report = _scan_contracts(Path(self.tmp))
        buf = StringIO()
        with patch('sys.stdout', buf):
            _render_report(report)
        output = buf.getvalue()
        self.assertIn('PyContract', output)
        self.assertIn('GoContract', output)


if __name__ == '__main__':
    unittest.main()
