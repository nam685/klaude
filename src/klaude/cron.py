"""cron — run a prompt or skill on a recurring interval.

A simple scheduler that runs within a klaude REPL session. Not a
system-level cron — it lives and dies with the session.

Usage from the REPL:
    /cron 5m read git_status and summarize changes
    /cron 10m /review
    /cron list
    /cron stop <id>
"""

import threading
import time
from dataclasses import dataclass, field


@dataclass
class CronJob:
    """A recurring scheduled job."""
    job_id: str
    interval_seconds: int
    prompt: str
    active: bool = True
    run_count: int = 0
    last_run: float | None = None
    _timer: threading.Timer | None = field(default=None, repr=False)


# Module-level job store
_jobs: dict[str, CronJob] = {}
_next_id = 1

# Callback set by REPL to schedule a turn
_run_callback: callable = None  # type: ignore[assignment]


def set_run_callback(callback: callable) -> None:  # type: ignore[type-arg]
    """Set the callback function that runs a prompt through the session.

    Called by repl.py to inject session.turn as the execution mechanism.
    """
    global _run_callback
    _run_callback = callback


def _parse_interval(spec: str) -> int | None:
    """Parse an interval like '5m', '30s', '1h' into seconds."""
    spec = spec.strip().lower()
    if spec.endswith("s"):
        try:
            return int(spec[:-1])
        except ValueError:
            return None
    if spec.endswith("m"):
        try:
            return int(spec[:-1]) * 60
        except ValueError:
            return None
    if spec.endswith("h"):
        try:
            return int(spec[:-1]) * 3600
        except ValueError:
            return None
    # Plain number = minutes
    try:
        return int(spec) * 60
    except ValueError:
        return None


def _schedule_next(job: CronJob) -> None:
    """Schedule the next run of a cron job."""
    if not job.active:
        return

    def _tick() -> None:
        if not job.active:
            return
        job.run_count += 1
        job.last_run = time.time()
        if _run_callback:
            try:
                _run_callback(job.prompt)
            except Exception:
                pass  # don't crash the timer thread
        _schedule_next(job)

    job._timer = threading.Timer(job.interval_seconds, _tick)
    job._timer.daemon = True
    job._timer.start()


def create_job(interval_spec: str, prompt: str) -> str:
    """Create and start a new cron job. Returns a status message."""
    global _next_id

    seconds = _parse_interval(interval_spec)
    if seconds is None or seconds < 10:
        return "Error: invalid interval (use e.g. '30s', '5m', '1h'; minimum 10s)"

    job_id = f"cron-{_next_id}"
    _next_id += 1

    job = CronJob(job_id=job_id, interval_seconds=seconds, prompt=prompt)
    _jobs[job_id] = job
    _schedule_next(job)

    # Format interval for display
    if seconds >= 3600:
        interval_str = f"{seconds // 3600}h"
    elif seconds >= 60:
        interval_str = f"{seconds // 60}m"
    else:
        interval_str = f"{seconds}s"

    return f"Started {job_id}: every {interval_str} → {prompt[:80]}"


def list_jobs() -> str:
    """List all cron jobs."""
    if not _jobs:
        return "No cron jobs."

    lines = ["Cron jobs:\n"]
    for job in _jobs.values():
        status = "active" if job.active else "stopped"
        interval = f"{job.interval_seconds}s"
        if job.interval_seconds >= 3600:
            interval = f"{job.interval_seconds // 3600}h"
        elif job.interval_seconds >= 60:
            interval = f"{job.interval_seconds // 60}m"
        runs = f"{job.run_count} runs"
        lines.append(f"  {job.job_id}: [{status}] every {interval}, {runs} — {job.prompt[:60]}")
    return "\n".join(lines)


def stop_job(job_id: str) -> str:
    """Stop a cron job."""
    if job_id not in _jobs:
        return f"Error: unknown job '{job_id}'"

    job = _jobs[job_id]
    job.active = False
    if job._timer:
        job._timer.cancel()
    return f"Stopped {job_id}"


def stop_all() -> str:
    """Stop all cron jobs."""
    if not _jobs:
        return "No cron jobs to stop."

    count = 0
    for job in _jobs.values():
        if job.active:
            job.active = False
            if job._timer:
                job._timer.cancel()
            count += 1
    return f"Stopped {count} cron job(s)"
