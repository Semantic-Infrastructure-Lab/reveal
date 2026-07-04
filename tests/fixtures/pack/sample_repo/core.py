"""Core domain logic — imported by api.py and util.py (high fan-in).

This is the high-signal file a token-budgeted pack should surface first: it is
the module the rest of the repo depends on, so an agent drilling into the repo
needs it before the leaf modules.
"""


def validate(order):
    """Reject malformed orders."""
    if order is None:
        raise ValueError("order required")
    if order.get("qty", 0) <= 0:
        return False
    return True


def price(order):
    """Compute the order total."""
    total = 0
    for item in order.get("items", []):
        total += item["unit"] * item["qty"]
    return total


def process_order(order):
    """Validate then price an order."""
    if not validate(order):
        return None
    return price(order)
