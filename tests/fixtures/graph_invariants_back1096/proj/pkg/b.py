from typing import TYPE_CHECKING

from pkg import a
from pkg.a import helper

if TYPE_CHECKING:
    from pkg import c


def go():
    helper()
    return a.run()


def later():
    from pkg import c
    return c.both()
