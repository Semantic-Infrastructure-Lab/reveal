"""ResourceSpec.address: the characters that start an address part of a resource beyond its path (BACK-2726).

A shared declaration, empty by default (every resource is its path). Git declares ``@`` (``git://app.py@main``): the
guide-migration script reads it to keep such a URI, where a plain path teaches the subcommand.
"""
from reveal.utils.query_parser import ResourceSpec


def test_the_address_is_empty_by_default_and_published_only_when_declared():
    assert ResourceSpec().address == '' and 'address' not in ResourceSpec().schema()
    assert ResourceSpec(address='@').schema()['address'] == '@'


def test_git_declares_its_ref_mark_and_no_other_noun_declares_one():
    from reveal.cli.invocation import COMMANDS
    from reveal.cli.routing.declared import declared_adapter_class
    declared = {name: declared_adapter_class(spec.declared_adapter) for name, spec in COMMANDS.items()
                if spec.declared_adapter}
    marks = {name: adapter.RESOURCE_SPEC.address for name, adapter in declared.items()
             if adapter is not None and adapter.RESOURCE_SPEC.address}
    assert marks == {'git': '@'}
