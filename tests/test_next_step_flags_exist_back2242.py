"""BACK-2242: the domain:// and ssl:// next-step hints named `--check-advanced`, which is not a flag
(argparse: unrecognized arguments, exit 2). The real spelling is `--check --advanced`.
"""
from pathlib import Path

import reveal
from reveal.cli.parser import create_argument_parser

_ADAPTERS = Path(reveal.__file__).parent / 'adapters'


def test_no_adapter_hint_uses_the_nonexistent_check_advanced_flag():
    offenders = [str(p.relative_to(_ADAPTERS)) for p in _ADAPTERS.rglob('*.py')
                 if '--check-advanced' in p.read_text(encoding='utf-8')]
    assert offenders == []


def test_the_suggested_spelling_parses():
    args = create_argument_parser('test').parse_args(['ssl://example.com', '--check', '--advanced'])
    assert args.check and args.advanced


def test_negative_control_the_old_spelling_does_not_parse():
    parser = create_argument_parser('test')
    try:
        parser.parse_args(['ssl://example.com', '--check-advanced'])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover
        raise AssertionError('--check-advanced parsed; the guard above is out of date')
