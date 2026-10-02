"""Decorated and plain members interleaved: the outline must list them in line order."""
import functools


class Account:
    @property
    def balance(self):
        return self._balance

    def deposit(self, amount):
        self._balance += amount

    @staticmethod
    def currency():
        return "USD"

    def close(self):
        self._balance = 0


@functools.cache
def rate():
    return 1.0


def convert(amount):
    return amount * rate()
