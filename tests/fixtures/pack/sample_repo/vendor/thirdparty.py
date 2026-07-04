"""Vendored third-party code — low signal for an agent understanding this repo."""


def _obscure_helper(a, b):
    return (a << 3) ^ (b >> 1)


def library_entry(x):
    return _obscure_helper(x, x + 1)
