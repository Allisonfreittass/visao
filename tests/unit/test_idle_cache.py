"""Heavy models in memory only while used (integrations/idle_cache.py, etapa 4)."""

import gc
import resource
import sys
import threading
import time

import pytest

from integrations.idle_cache import VOICE_IDLE, IdleCache, IdleLimit
from integrations.stt.engine import load_stt
from integrations.tts.catalog import load_provider


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_the_same_model_while_used_and_gone_after_the_limit():
    loads = []
    clock = Clock()
    cache = IdleCache(
        lambda size: loads.append(size) or object(), idle_seconds=lambda: 600, clock=clock
    )

    first = cache("base")
    clock.now = 500
    assert cache("base") is first  # used again before the limit: kept, and the clock restarts
    clock.now = 1000
    assert cache.sweep() == 0  # 500 s since the last use
    clock.now = 1100
    assert cache.sweep() == 1
    assert len(cache) == 0
    assert cache("base") is not first  # loaded again on the next use
    assert loads == ["base", "base"]


def test_a_request_holding_the_model_finishes_with_it():
    clock = Clock()
    cache = IdleCache(lambda: {"model": "kokoro"}, idle_seconds=lambda: 10, clock=clock)
    in_hand = cache()
    clock.now = 60
    cache.sweep()
    assert in_hand == {"model": "kokoro"}  # the cache let go; the caller still has it


def test_zero_keeps_it_for_the_life_of_the_process():
    clock = Clock()
    cache = IdleCache(object, idle_seconds=lambda: 0, clock=clock)
    cache()
    clock.now = 10**9
    assert cache.sweep() == 0
    assert len(cache) == 1


def test_at_most_maxsize_models_the_oldest_goes_first():
    cache = IdleCache(lambda voice: voice, idle_seconds=lambda: 600, maxsize=2)
    cache("pf_dora")
    cache("pm_alex")
    cache("pf_dora")  # used again: now the newest
    cache("piper")
    assert len(cache) == 2
    assert cache("pf_dora") == "pf_dora"


def test_one_load_when_two_requests_arrive_together():
    loads = []
    started = threading.Event()

    def slow_load():
        loads.append(1)
        started.set()
        time.sleep(0.2)
        return object()

    cache = IdleCache(slow_load, idle_seconds=lambda: 600)
    results = []
    threads = [threading.Thread(target=lambda: results.append(cache())) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results[0] is results[1]  # both get the one that stayed in the cache


def test_the_sweeper_thread_unloads_by_itself_and_then_ends():
    cache = IdleCache(object, idle_seconds=lambda: 0.2, name="teste")
    cache()
    deadline = time.monotonic() + 5
    while len(cache) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert len(cache) == 0
    deadline = time.monotonic() + 5
    while cache._sweeper is not None and time.monotonic() < deadline:
        time.sleep(0.1)
    assert cache._sweeper is None  # nothing left to watch: the thread is gone


@pytest.mark.skipif(sys.platform != "linux", reason="reads /proc/self/statm")
def test_the_memory_really_goes_back():
    """A stand-in for a model: 300 MB that the process gets back once the cache lets go."""

    def rss_mb() -> float:
        with open("/proc/self/statm") as statm:
            return int(statm.read().split()[1]) * resource.getpagesize() / 2**20

    clock = Clock()
    cache = IdleCache(lambda: bytearray(300 * 2**20), idle_seconds=lambda: 1, clock=clock)
    before = rss_mb()
    model = cache()
    model[::4096] = b"x" * len(model[::4096])  # touch every page so it is really resident
    del model
    loaded = rss_mb()
    clock.now = 5
    cache.sweep()
    gc.collect()
    after = rss_mb()
    assert loaded - before > 250
    assert loaded - after > 250


def test_the_voice_loaders_are_idle_caches_with_the_app_limit():
    assert isinstance(load_stt, IdleCache) and isinstance(load_provider, IdleCache)
    assert isinstance(VOICE_IDLE, IdleLimit)
    VOICE_IDLE.set(42)
    assert load_stt._idle_seconds() == 42 and load_provider._idle_seconds() == 42
    VOICE_IDLE.set(600)
