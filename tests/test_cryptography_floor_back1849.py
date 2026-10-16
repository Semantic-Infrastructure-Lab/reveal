"""pyproject's cryptography floor must cover the API ssl/certificate.py calls (BACK-1849).

``not_valid_before_utc`` / ``not_valid_after_utc`` arrived in cryptography 42; with the
floor at 41 a 41.x install made every unverifiable certificate fail to parse.
"""
import re
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / 'pyproject.toml'
CERTIFICATE = Path(__file__).resolve().parent.parent / 'reveal' / 'adapters' / 'ssl' / 'certificate.py'
UTC_API_ADDED_IN = 42


def test_floor_covers_the_utc_validity_accessors():
    assert 'not_valid_before_utc' in CERTIFICATE.read_text(encoding='utf-8'), \
        "certificate.py no longer uses the 42+ accessor: re-evaluate this floor"
    floor = re.search(r'"cryptography>=(\d+)', PYPROJECT.read_text(encoding='utf-8'))
    assert floor and int(floor.group(1)) >= UTC_API_ADDED_IN
