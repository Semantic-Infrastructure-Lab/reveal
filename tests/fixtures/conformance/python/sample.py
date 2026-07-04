"""Conformance fixture (BACK-422 Tier 1) — Python reference implementation."""
import os
import sys  # unused on purpose — must still be flagged by imports://


def validate(order):
    if not order:
        raise ValueError("empty order")
    return order


def process_order(order):
    result = validate(order)
    try:
        log_path = os.path.join("/tmp", "orders.log")
        with open(log_path, "a") as f:
            f.write(str(result))
    except OSError:
        return None
    result = result.upper()
    return result


def run(order):
    return process_order(order)


class Batch:
    """BACK-439b/c fixture addition: loop + field write + call effect,
    added standalone (not touching process_order's line-numbered asserts),
    same precedent as Rust's count_down (BACK-427/430)."""

    def __init__(self):
        self.total = 0

    def run(self, items):
        for item in items:
            self.total = self.total + item
            cache.set(item)
        return self.total
