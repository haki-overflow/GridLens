"""Background jobs: long work runs on its own thread, with progress and cancel.

start(kind, work)  queue work(progress); work calls progress(stage, done,
                   total) as it goes (total None when unknown) and returns
                   the result. One job of each kind runs at a time, oldest
                   first; kinds never wait for each other (a layout does not
                   wait behind a study)
get(id)            a JSON-ready snapshot: status, stage, done / total, elapsed,
                   eta, and the result (done) or problems (failed)
cancel(id)         the job is cancelled at once and the next one of its kind
                   starts; its work stops at its next progress call (a long
                   step in between, such as one big factorisation, finishes
                   unseen and its answer is dropped)
listing()          every kept job, without results

Finished jobs are kept (the last KEEP) so a client can still fetch the
result. No maths here: the API passes in the work to run.
"""
import threading
import time
import uuid

KEEP = 8
ENDED = ("done", "failed", "cancelled")

_lock = threading.Lock()   # guards the registry and every job's fields
_jobs = {}                 # id -> Job, oldest first


class Cancelled(BaseException):
    """Raised inside a job by progress() after cancel(). A BaseException, so
    the studies' `except Exception` (an outage that does not solve) and the
    API's error guard never mistake it for a failed solve."""


class Job:
    def __init__(self, kind, work):
        self.id, self.kind, self.work = uuid.uuid4().hex[:12], kind, work
        self.status, self.stage, self.done, self.total = "queued", "Queued", 0, None
        self.started = self.stage_t = self.ended = None
        self.result, self.problems, self.notes = None, [], []
        self.stop = threading.Event()

    def progress(self, stage, done, total=None):
        if self.stop.is_set():
            raise Cancelled
        with _lock:
            if stage != self.stage:
                self.stage, self.stage_t = stage, time.monotonic()
            self.done, self.total = done, total

    def run(self, work):
        problems, notes = [], []
        try:
            result, status = work(self.progress), "done"
        except Cancelled:
            result, status = None, "cancelled"
        except Exception as e:  # noqa: BLE001 - reported to the client as problems
            result, status = None, "failed"
            problems = list(getattr(e, "problems", None) or [str(e) or type(e).__name__])
            notes = list(getattr(e, "notes", []))
        with _lock:
            if self.status == "running":       # not cancelled in the meantime
                self.result, self.status, self.problems, self.notes = result, status, problems, notes
                self.ended, self.work = time.monotonic(), None
        _next(self.kind)

    def snapshot(self, result=True):
        with _lock:
            now = self.ended or time.monotonic()
            eta = None
            if self.status == "running" and self.total and self.done:
                eta = round((now - self.stage_t) / self.done * (self.total - self.done), 1)
            out = dict(id=self.id, kind=self.kind, status=self.status, stage=self.stage,
                       done=self.done, total=self.total,
                       elapsed=round(now - self.started, 2) if self.started else 0.0, eta=eta)
            if self.status == "done" and result:
                out["result"] = self.result
            if self.status == "failed":
                out.update(problems=self.problems, notes=self.notes)
            return out


def _next(kind):
    """Start the oldest queued job of this kind unless one of its kind runs."""
    with _lock:
        if any(j.kind == kind and j.status == "running" for j in _jobs.values()):
            return
        job = next((j for j in _jobs.values() if j.kind == kind and j.status == "queued"), None)
        if job is None:
            return
        job.status, job.started = "running", time.monotonic()
        job.stage_t = job.started
        work = job.work
    threading.Thread(target=job.run, args=(work,), name=f"gridlens-{kind}", daemon=True).start()


def start(kind, work):
    """Queue work(progress) and return the new job's snapshot."""
    job = Job(kind, work)
    with _lock:
        _jobs[job.id] = job
        ended = [k for k, j in _jobs.items() if j.status in ENDED]
        for k in ended[:max(0, len(_jobs) - KEEP)]:
            del _jobs[k]
    _next(kind)
    return job.snapshot()


def get(job_id):
    """The job's snapshot (with the result when done), or None."""
    job = _jobs.get(job_id)
    return job.snapshot() if job else None


def cancel(job_id):
    """Cancel a queued or running job (see the module notes). Returns its
    snapshot, or None for an unknown id."""
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        if job.status in ("queued", "running"):
            job.stop.set()
            job.status, job.ended, job.work = "cancelled", time.monotonic(), None
    _next(job.kind)
    return job.snapshot()


def listing():
    with _lock:
        kept = list(_jobs.values())
    return [j.snapshot(result=False) for j in kept]
