"""``request_cache.in_host_request()``: is this thread inside ``host_request()`` (BACK-2109)?

A lazily filled validated cache reads and stores only inside a host request, where entry
revalidates and exit seals its entries; outside one (a CLI run, a direct library call)
nothing would.
"""
import threading

from reveal.utils import request_cache


def test_false_outside_any_request():
    assert request_cache.in_host_request() is False


def test_true_inside_a_request_and_a_nested_one_and_false_after():
    with request_cache.host_request():
        assert request_cache.in_host_request() is True
        with request_cache.host_request():
            assert request_cache.in_host_request() is True
        assert request_cache.in_host_request() is True
    assert request_cache.in_host_request() is False


def test_false_after_a_request_that_raised():
    try:
        with request_cache.host_request():
            raise KeyError('boom')
    except KeyError:
        pass
    assert request_cache.in_host_request() is False


def test_another_threads_request_does_not_count():
    """A worker thread started inside a request, or any thread while another holds one."""
    seen = []
    with request_cache.host_request():
        worker = threading.Thread(target=lambda: seen.append(request_cache.in_host_request()))
        worker.start()
        worker.join(timeout=30)
    assert seen == [False]
