"""Tests for reveal.utils.threadsafe.main_thread_gc."""

import gc
import unittest

from reveal.utils.threadsafe import main_thread_gc


class TestMainThreadGc(unittest.TestCase):
    """main_thread_gc suspends automatic GC inside the block and restores state."""

    def tearDown(self):
        # Never leave the collector disabled for other tests.
        gc.enable()

    def test_gc_disabled_inside_block(self):
        """Automatic collection is off inside the block (worker threads can't run it)."""
        gc.enable()
        with main_thread_gc():
            self.assertFalse(gc.isenabled(), "GC should be suspended inside the block")
        self.assertTrue(gc.isenabled(), "GC should be re-enabled after the block")

    def test_restores_disabled_state(self):
        """If GC was already disabled, it stays disabled afterward."""
        gc.disable()
        try:
            with main_thread_gc():
                self.assertFalse(gc.isenabled())
            self.assertFalse(gc.isenabled(), "Prior disabled state must be preserved")
        finally:
            gc.enable()

    def test_restores_on_exception(self):
        """GC state is restored even if the block raises."""
        gc.enable()
        with self.assertRaises(ValueError):
            with main_thread_gc():
                raise ValueError("boom")
        self.assertTrue(gc.isenabled(), "GC must be re-enabled after an exception")

    def test_nesting_is_safe(self):
        """Nested use restores the outer enabled state correctly."""
        gc.enable()
        with main_thread_gc():
            with main_thread_gc():
                self.assertFalse(gc.isenabled())
            # Inner exit saw was_enabled=False (GC already off), so it leaves it off.
            self.assertFalse(gc.isenabled())
        self.assertTrue(gc.isenabled(), "Outermost block restores enabled state")


if __name__ == '__main__':
    unittest.main()
