"""Concurrency-bounded background runner for BeCertain analyze jobs."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Dict, Optional


class BeCertainAnalyzeJobRunnerService:
    def __init__(self, *, max_concurrency: int) -> None:
        self._semaphore = asyncio.Semaphore(max(1, int(max_concurrency)))
        self._tasks: Dict[str, asyncio.Task] = {}

    async def _run_with_limit(self, *, job_id: str, run_fn: Callable[[], Awaitable[None]]) -> None:
        async with self._semaphore:
            await run_fn()

    def submit(self, *, job_id: str, run_fn: Callable[[], Awaitable[None]]) -> asyncio.Task:
        existing = self._tasks.get(job_id)
        if existing and not existing.done():
            return existing

        task = asyncio.create_task(self._run_with_limit(job_id=job_id, run_fn=run_fn))
        self._tasks[job_id] = task

        def _cleanup(done_task: asyncio.Task) -> None:
            current = self._tasks.get(job_id)
            if current is done_task:
                self._tasks.pop(job_id, None)

        task.add_done_callback(_cleanup)
        return task

    def get_task(self, job_id: str) -> Optional[asyncio.Task]:
        task = self._tasks.get(job_id)
        if task and task.done():
            self._tasks.pop(job_id, None)
            return None
        return task
