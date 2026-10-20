"""A cooperative, independently scheduled demonstration worker.

v0.1 simulates a long task. No real papers or scientific data are analyzed.
"""

import asyncio
from .store import Store


class Worker:
    def __init__(self, store: Store):
        self.store = store
        self.active: dict[str, asyncio.Task] = {}

    def start(self, task_id: str) -> None:
        if task_id in self.active:
            raise ValueError("Task is already running")
        job = asyncio.create_task(self._run(task_id), name=f"nespa-{task_id}")
        self.active[task_id] = job
        job.add_done_callback(lambda _job: self.active.pop(task_id, None))

    async def _run(self, task_id: str) -> None:
        try:
            task = self.store.get_task(task_id)
            if not task:
                return
            self.store.change_status(task_id, "running", "started", "Worker 已开始执行模拟任务。")
            for step in range(1, task["total_steps"] + 1):
                await asyncio.sleep(task["interval_ms"] / 1000)
                self.store.advance(task_id, step)
            self.store.change_status(task_id, "completed", "completed", "模拟任务完成。")
        except asyncio.CancelledError:
            self.store.change_status(task_id, "interrupted", "interrupted", "Worker 被关闭，任务未完成。")
            raise
        except Exception as exc:
            self.store.change_status(task_id, "failed", "failed", f"Worker failed: {type(exc).__name__}")

    async def close(self) -> None:
        jobs = list(self.active.values())
        for job in jobs:
            job.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
