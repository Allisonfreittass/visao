"""A cache that forgets what sat unused: heavy models in memory only while they are being used
(docs/research/execucao_local.md, etapa 4).

The voice models load on first use (Kokoro ~0.9 GB, Whisper `base` ~0.5 GB) and an lru_cache kept
them for the life of the process, so on an 8 GB machine they held their memory for hours after the
last word. An IdleCache keeps the same call (`load(*key)` returns the same object while it is in
use) and drops an entry after `idle_seconds()` without a call. Dropping only lets go of the cache's
reference: a request still holding the object finishes with it, and the memory goes after that.
A daemon thread does the sweeping, started with the first entry and gone when the cache is empty.
"""

import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MIN_SWEEP_SECONDS = 1.0
MAX_SWEEP_SECONDS = 60.0


class IdleLimit:
    """A limit in seconds that the app sets at start (from its settings), read on every sweep."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def set(self, seconds: float) -> None:
        self.seconds = seconds

    def __call__(self) -> float:
        return self.seconds


# How long a voice model may sit unused before it leaves memory (VISION_VOICE_IDLE_MINUTES).
VOICE_IDLE = IdleLimit(600.0)


@dataclass
class _Entry[T]:
    value: T
    last_used: float


class IdleCache[T]:
    def __init__(
        self,
        load: Callable[..., T],
        *,
        idle_seconds: Callable[[], float],
        maxsize: int = 1,
        name: str = "cache",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._load = load
        self._idle_seconds = idle_seconds
        self._maxsize = maxsize
        self._name = name
        self._clock = clock
        self._entries: OrderedDict[Hashable, _Entry[T]] = OrderedDict()
        self._lock = threading.Lock()
        self._sweeper: threading.Thread | None = None

    def __call__(self, *key: Hashable) -> T:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                entry.last_used = self._clock()
                self._entries.move_to_end(key)
                return entry.value
        # Loading is slow (seconds): outside the lock, so other keys are not held up.
        value = self._load(*key)
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:  # another call loaded it meanwhile: keep one
                entry.last_used = self._clock()
                return entry.value
            self._entries[key] = _Entry(value, self._clock())
            while len(self._entries) > self._maxsize:
                self._entries.popitem(last=False)
            self._start_sweeper()
        return value

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def cache_clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def sweep(self) -> int:
        """Drops what sat unused past the limit; returns how many went. Zero or less: never."""
        limit = self._idle_seconds()
        if limit <= 0:
            return 0
        now = self._clock()
        with self._lock:
            stale = [k for k, e in self._entries.items() if now - e.last_used >= limit]
            for key in stale:
                del self._entries[key]
        if stale:
            logger.info(
                "%s unloaded after %.0f s idle",
                self._name,
                limit,
                extra={"event": "idle_unloaded", "cache": self._name, "count": len(stale)},
            )
        return len(stale)

    def _start_sweeper(self) -> None:
        """Called with the lock held, after an entry went in."""
        if self._sweeper is not None and self._sweeper.is_alive():
            return
        self._sweeper = threading.Thread(
            target=self._sweep_loop, name=f"{self._name}-idle", daemon=True
        )
        self._sweeper.start()

    def _sweep_loop(self) -> None:
        while True:
            limit = self._idle_seconds()
            pause = min(MAX_SWEEP_SECONDS, max(MIN_SWEEP_SECONDS, limit / 4 if limit > 0 else 60))
            time.sleep(pause)
            self.sweep()
            with self._lock:
                if not self._entries:
                    self._sweeper = None
                    return
