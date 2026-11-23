"""A declared resource spelled in several words (``ResourceSpec.parts``, BACK-2214): the subcommand takes one positional
per word, the first required as the resource is, and the words join into the one resource its URI names
(``reveal diff a.py b.py`` is ``diff://a.py:b.py``); one word is the resource as the URI spells it. A URI request's own
parser (``create_declared_parser(uri_request=True)``) reads the URI's path as the one positional named ``name``.

Shared owners: ``utils/query_parser.ResourceSpec``, ``utils/query_binding.add_declared_arguments`` and
``typed_resource``, ``cli/routing/declared.py`` (the parser and every reader of the resource positional). Effect on
every noun: a noun that declares no parts (all of them but diff) gets the same one positional on both parsers, and
``typed_resource`` reads it as ``getattr(args, name)`` did.
"""
import argparse

import pytest

from reveal.cli.invocation import COMMANDS
from reveal.cli.routing.declared import create_declared_parser, declared_adapter_class
from reveal.utils.query_binding import add_declared_arguments, typed_resource
from reveal.utils.query_parser import ResourceSpec

pytestmark = [pytest.mark.unit]

PAIR = ResourceSpec(name='pair', cli_default=None, uri_default='', required=True, filesystem=False,
                    parts=('left', 'right'), joiner=':')


def _parser(spec, **kwargs):
    parser = argparse.ArgumentParser(prog='reveal noun')
    add_declared_arguments(parser, (), spec, **kwargs)
    return parser


def test_each_word_is_a_positional_and_the_words_join():
    args = _parser(PAIR).parse_args(['a.py', 'b.py/ok'])
    assert (args.left, args.right) == ('a.py', 'b.py/ok')
    assert typed_resource(PAIR, args) == 'a.py:b.py/ok'


def test_one_word_is_the_resource_as_the_uri_spells_it():
    assert typed_resource(PAIR, _parser(PAIR).parse_args(['a.py:b.py'])) == 'a.py:b.py'


def test_the_first_word_is_required_as_the_resource_is():
    with pytest.raises(SystemExit):
        _parser(PAIR).parse_args([])
    optional = ResourceSpec(name='pair', cli_default='', parts=('left', 'right'), joiner=':')
    assert typed_resource(optional, _parser(optional).parse_args([])) == ''


def test_a_uri_requests_parser_reads_the_one_positional():
    parser = _parser(PAIR, joined=True)
    args, extras = parser.parse_known_args(['a.py:b.py', 'ok'])
    assert args.pair == 'a.py:b.py' and extras == ['ok'] and not hasattr(args, 'left')
    assert typed_resource(PAIR, args) == 'a.py:b.py'


def test_a_resource_without_parts_is_unchanged():
    plain = ResourceSpec(name='path')
    for joined in (False, True):
        args = _parser(plain, joined=joined).parse_args(['src'])
        assert args.path == 'src' and typed_resource(plain, args) == 'src'
    assert 'parts' not in plain.schema() and PAIR.schema()['parts'] == ['left', 'right']


def _positionals(parser):
    return [action.dest for action in parser._actions if not action.option_strings and action.dest != 'help']


def test_every_declared_noun_reads_its_resource_on_both_parsers():
    """Effect on every noun: the subcommand and the URI request read the same one positional, except a noun whose
    resource declares parts (diff), whose subcommand takes the words."""
    for noun, spec in sorted(COMMANDS.items()):
        adapter = declared_adapter_class(spec.declared_adapter) if spec.declared_adapter else None
        if adapter is None:
            continue
        resource = adapter.RESOURCE_SPEC
        typed, uri = (_positionals(create_declared_parser(noun, uri_request=flag)) for flag in (False, True))
        assert uri == [resource.name], (noun, uri)
        assert typed == (list(resource.parts) or [resource.name]), (noun, typed)
