"""Bounded worker, turn, and WebSocket connection admission."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import threading
from collections import deque


class ExecutorSaturatedError(RuntimeError):
    """A bounded executor rejected work instead of growing its private queue."""


async def run_bounded(executor: BoundedThreadPoolExecutor, fn, /, *args):
    """Run one blocking operation only when its finite executor admits it."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, fn, *args)


class BoundedThreadPoolExecutor(concurrent.futures.ThreadPoolExecutor):
    """ThreadPoolExecutor with a hard cap on running plus queued futures."""

    def __init__(self, *, max_workers: int, max_outstanding: int, thread_name_prefix: str) -> None:
        if max_outstanding < max_workers:
            raise ValueError("max_outstanding must cover every worker")
        self._permits = threading.BoundedSemaphore(max_outstanding)
        super().__init__(max_workers=max_workers, thread_name_prefix=thread_name_prefix)

    def submit(self, fn, /, *args, **kwargs):
        if not self._permits.acquire(blocking=False):
            raise ExecutorSaturatedError("blocking worker admission is full")
        try:
            future = super().submit(fn, *args, **kwargs)
        except BaseException:
            self._permits.release()
            raise
        future.add_done_callback(lambda _completed: self._permits.release())
        return future


class TurnAdmission:
    """Process-global FIFO turn semaphore with an exact finite waiter bound."""

    def __init__(self, active_limit: int, queue_limit: int) -> None:
        if active_limit < 1 or queue_limit < 0:
            raise ValueError("turn admission limits are invalid")
        self.active_limit = active_limit
        self.queue_limit = queue_limit
        self._guard = threading.Lock()
        self._active = 0
        self._waiting: deque[TurnLease] = deque()

    def reserve(self) -> TurnLease | None:
        loop = asyncio.get_running_loop()
        with self._guard:
            if self._active < self.active_limit:
                self._active += 1
                return TurnLease(self, loop, active=True)
            if len(self._waiting) >= self.queue_limit:
                return None
            lease = TurnLease(self, loop, active=False)
            self._waiting.append(lease)
            return lease

    def snapshot(self) -> tuple[int, int]:
        with self._guard:
            return self._active, len(self._waiting)

    def _release(self, lease: TurnLease) -> None:
        promote = None
        with self._guard:
            if lease._state == "released":
                return
            if lease._state == "queued":
                lease._state = "released"
                with contextlib.suppress(ValueError):
                    self._waiting.remove(lease)
                return
            lease._state = "released"
            while self._waiting:
                candidate = self._waiting.popleft()
                if candidate._state == "queued":
                    candidate._state = "active"
                    promote = candidate
                    break
            if promote is None:
                self._active -= 1
        if promote is not None:
            try:
                promote._loop.call_soon_threadsafe(promote._grant)
            except RuntimeError:
                promote.release()


class TurnLease:
    def __init__(
        self,
        admission: TurnAdmission,
        loop: asyncio.AbstractEventLoop,
        *,
        active: bool,
    ) -> None:
        self._admission = admission
        self._loop = loop
        self._ready = loop.create_future()
        self._state = "active" if active else "queued"
        if active:
            self._ready.set_result(None)

    def _grant(self) -> None:
        if not self._ready.done():
            self._ready.set_result(None)

    async def __aenter__(self) -> TurnLease:
        try:
            await self._ready
        except BaseException:
            self.release()
            raise
        return self

    async def __aexit__(self, *_exc) -> None:
        self.release()

    def release(self) -> None:
        self._admission._release(self)

    def cancel_if_queued(self) -> bool:
        """Atomically remove a waiting turn so it can never be promoted later."""
        with self._admission._guard:
            if self._state != "queued":
                return False
            self._state = "released"
            with contextlib.suppress(ValueError):
                self._admission._waiting.remove(self)
            return True


class WsConnectionAdmission:
    """Hard process/account/Team bounds for sockets and their one ask poller."""

    def __init__(self, global_limit: int, account_limit: int, team_limit: int) -> None:
        if min(global_limit, account_limit, team_limit) < 1:
            raise ValueError("WebSocket connection limits must be positive")
        self.global_limit = global_limit
        self.account_limit = account_limit
        self.team_limit = team_limit
        self._guard = threading.Lock()
        self._global = 0
        self._accounts: dict[str, int] = {}
        self._teams: dict[tuple[str, str], int] = {}

    def reserve(self, account_id: str, team_id: str) -> WsConnectionLease | None:
        team_key = (account_id, team_id)
        with self._guard:
            if (
                self._global >= self.global_limit
                or self._accounts.get(account_id, 0) >= self.account_limit
                or self._teams.get(team_key, 0) >= self.team_limit
            ):
                return None
            self._global += 1
            self._accounts[account_id] = self._accounts.get(account_id, 0) + 1
            self._teams[team_key] = self._teams.get(team_key, 0) + 1
        return WsConnectionLease(self, account_id, team_key)

    def snapshot(self) -> tuple[int, dict[str, int], dict[tuple[str, str], int]]:
        with self._guard:
            return self._global, dict(self._accounts), dict(self._teams)

    def _release(self, lease: WsConnectionLease) -> None:
        with self._guard:
            if lease._released:
                return
            lease._released = True
            self._global -= 1
            account_count = self._accounts[lease._account_id] - 1
            team_count = self._teams[lease._team_key] - 1
            if account_count:
                self._accounts[lease._account_id] = account_count
            else:
                del self._accounts[lease._account_id]
            if team_count:
                self._teams[lease._team_key] = team_count
            else:
                del self._teams[lease._team_key]


class WsConnectionLease:
    def __init__(
        self,
        admission: WsConnectionAdmission,
        account_id: str,
        team_key: tuple[str, str],
    ) -> None:
        self._admission = admission
        self._account_id = account_id
        self._team_key = team_key
        self._released = False

    def release(self) -> None:
        self._admission._release(self)
