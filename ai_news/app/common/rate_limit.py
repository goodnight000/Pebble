from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class TokenBucket:
    rate_per_sec: float
    capacity: float
    tokens: float
    last_refill: float

    def refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.last_refill = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_sec)

    async def acquire(self) -> None:
        while True:
            self.refill()
            if self.tokens >= 1:
                self.tokens -= 1
                return
            await asyncio.sleep(max(0.01, 1 / max(self.rate_per_sec, 0.01)))


class DomainRateLimiter:
    def __init__(self, max_concurrency: int = 10) -> None:
        self._buckets = {}
        self._lock = asyncio.Lock()
        self._global_sem = asyncio.Semaphore(max_concurrency)

    async def acquire(self, domain: str, rate_per_sec: float) -> None:
        rate_per_sec = max(0.1, min(rate_per_sec, 1.0))
        async with self._lock:
            bucket = self._buckets.get(domain)
            if bucket is None:
                bucket = TokenBucket(rate_per_sec, capacity=1.0, tokens=1.0, last_refill=time.monotonic())
                self._buckets[domain] = bucket
        await self._global_sem.acquire()
        try:
            await bucket.acquire()
        finally:
            self._global_sem.release()


rate_limiter = DomainRateLimiter()
