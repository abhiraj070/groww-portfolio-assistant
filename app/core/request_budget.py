"""Single-process inbound budget, including authentication failures, without logging identity."""

import time
from collections import deque
from collections.abc import Callable
from threading import Lock

from app.core.exceptions import ServiceError


class RequestBudget:
    def __init__(self, limit: int, clock: Callable[[], float] = time.monotonic):
        self.limit, self.clock = limit, clock
        self.events = deque()
        self.lock = Lock()

    def acquire(self):
        with self.lock:
            now = self.clock()
            while self.events and self.events[0] <= now - 60:
                self.events.popleft()
            if len(self.events) >= self.limit:
                raise ServiceError(
                    "request_rate_limited",
                    "Local API request limit reached",
                    429,
                    max(1, int(self.events[0] + 60 - now) + 1),
                )
            self.events.append(now)
