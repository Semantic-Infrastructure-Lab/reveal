"""Small helpers — depends on core."""

from core import price


def format_receipt(order):
    return f"Total: {price(order)}"
