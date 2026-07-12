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


if __name__ == '__main__':
    unittest.main()
