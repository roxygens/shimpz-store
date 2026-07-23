"""Shared admission budget for Store control-plane operations."""

from app.concurrency import BoundedThreadPoolExecutor
from app.config import CONTROL_QUEUE_MAX, CONTROL_WORKER_THREADS

EXECUTOR = BoundedThreadPoolExecutor(
    max_workers=CONTROL_WORKER_THREADS,
    max_outstanding=CONTROL_WORKER_THREADS + CONTROL_QUEUE_MAX,
    thread_name_prefix="shimpz-control",
)
