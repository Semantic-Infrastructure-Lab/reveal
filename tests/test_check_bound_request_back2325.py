"""``factory.check_bound_request`` runs a noun's own request checks, the ones the CLI's declared route runs before the
noun answers (``declared._validate_bound_request``); the Python API's URI form runs them through it too (BACK-2325)."""
from argparse import Namespace

import pytest

from reveal.adapters.factory import check_bound_request


class _Both:
    calls: list = []

    @staticmethod
    def validate_request(params, args):
        _Both.calls.append(('request', params, args))

    @classmethod
    def validate_request_at(cls, params, path, args):
        cls.calls.append(('at', params, path, args))


class _Refusing:
    @staticmethod
    def validate_request(params, args):
        raise ValueError('no such request')


def test_each_check_the_noun_declares_runs_in_order():
    _Both.calls = []
    args = Namespace()
    check_bound_request(_Both, {'k': 1}, 'p', args)
    assert _Both.calls == [('request', {'k': 1}, args), ('at', {'k': 1}, 'p', args)]


def test_a_refusal_propagates_as_raised():
    with pytest.raises(ValueError, match='no such request'):
        check_bound_request(_Refusing, {}, 'p', Namespace())


def test_a_noun_without_checks_is_not_checked():
    check_bound_request(object, {}, 'p', Namespace())
