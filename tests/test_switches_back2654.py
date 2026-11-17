"""Switches (BACK-2654 rule 15, COMMAND_MODEL "Switches"): positive names with on/off values sharing one codec."""
import pytest

from reveal.adapters.git.params import merge_policy
from reveal.utils.query_binding import switch_value


@pytest.mark.parametrize('value, expected', [
    ('on', True), ('off', False), ('ON', True), ('Off', False),
    ('true', True), ('false', False), ('yes', True), ('no', False), ('1', True), ('0', False),
    (True, True), (False, False),
])
def test_the_shared_switch_codec_reads_on_off_and_booleans(value, expected):
    assert switch_value(value) is expected


@pytest.mark.parametrize('value', ['maybe', '', 'enabled', 2, None])
def test_the_shared_switch_codec_rejects_other_values(value):
    with pytest.raises(ValueError):
        switch_value(value)


@pytest.mark.parametrize('value, include, legacy', [
    ('on', True, False), ('OFF', False, False), ('true', True, True), ('0', False, True), (False, False, False),
])
def test_git_merges_reads_the_shared_codec_and_remembers_a_legacy_boolean(value, include, legacy):
    policy = merge_policy(value)
    assert (policy.include, policy.legacy) == (include, legacy)
