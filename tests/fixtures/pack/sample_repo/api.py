"""HTTP-ish entry point — depends on core."""

from core import process_order, validate


def handle_request(payload):
    if not validate(payload):
        return {"status": 400}
    total = process_order(payload)
    return {"status": 200, "total": total}
