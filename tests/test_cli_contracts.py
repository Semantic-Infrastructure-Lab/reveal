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


if __name__ == '__main__':
    unittest.main()
