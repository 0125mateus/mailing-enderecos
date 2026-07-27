import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

_jobs: dict[str, "AutomationJob"] = {}
_lock = threading.Lock()


@dataclass
class AutomationJob:
    id: str
    total: int
    status: str = "pending"
    current: int = 0
    current_address: str = ""
    message: str = ""
    result: dict[str, Any] | None = None
    cancel_requested: bool = False
    thread: threading.Thread | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "total": self.total,
            "current": self.current,
            "current_address": self.current_address,
            "message": self.message,
            "result": self.result,
        }


def _run_job(job: AutomationJob, addresses: list[str]) -> None:
    from .maps_automation import search_addresses_on_map

    job.status = "running"

    def on_progress(current: int, total: int, address: str) -> None:
        job.current = current
        job.current_address = address

    try:
        job.result = search_addresses_on_map(
            addresses,
            on_progress=on_progress,
            should_cancel=lambda: job.cancel_requested,
        )
        if job.cancel_requested:
            job.status = "cancelled"
            job.message = "Automação cancelada pelo usuário."
        else:
            job.status = "completed"
            job.message = "Pesquisa concluída no Google My Maps."
    except ValueError as exc:
        job.status = "failed"
        job.message = str(exc)
    except Exception:
        job.status = "failed"
        job.message = (
            "Erro inesperado ao executar o Playwright. "
            "Verifique se o Chromium está instalado (playwright install chromium)."
        )


def create_job(addresses: list[str]) -> AutomationJob:
    job_id = uuid.uuid4().hex
    job = AutomationJob(id=job_id, total=len(addresses))

    with _lock:
        _jobs[job_id] = job

    thread = threading.Thread(
        target=_run_job,
        args=(job, addresses),
        daemon=True,
        name=f"maps-automation-{job_id[:8]}",
    )
    job.thread = thread
    thread.start()
    return job


def get_job(job_id: str) -> AutomationJob | None:
    with _lock:
        return _jobs.get(job_id)


def cancel_job(job_id: str) -> AutomationJob | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        if job.status in {"completed", "failed", "cancelled"}:
            return job
        job.cancel_requested = True
        return job
