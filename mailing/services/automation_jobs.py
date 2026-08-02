import json
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings

from .job_store import addresses_path, read_job, update_job, write_job

_active_job_id: str | None = None
ACTIVE_STATUSES = frozenset({"pending", "running", "paused"})


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


def _job_from_data(data: dict[str, Any]) -> AutomationJob:
    return AutomationJob(
        id=data["id"],
        total=data["total"],
        status=data["status"],
        current=data.get("current", 0),
        current_address=data.get("current_address", ""),
        message=data.get("message", ""),
        result=data.get("result"),
        cancel_requested=data.get("cancel_requested", False),
    )


def _refresh_active_job() -> None:
    global _active_job_id
    if not _active_job_id:
        return
    data = read_job(_active_job_id)
    if not data or data.get("status") not in ACTIVE_STATUSES:
        _active_job_id = None


def _jobs_dir() -> Path:
    return Path(settings.BASE_DIR) / "playwright" / "jobs"


def _list_job_ids_with_statuses(statuses: frozenset[str] | set[str]) -> list[str]:
    job_ids: list[str] = []
    jobs_dir = _jobs_dir()
    if not jobs_dir.is_dir():
        return job_ids

    for path in jobs_dir.glob("*.json"):
        if path.name.endswith("-addresses.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("status") in statuses and data.get("id"):
            job_ids.append(str(data["id"]))
    return job_ids


def _job_process_running(job_id: str) -> bool:
    needle = f"run_maps_job {job_id}"
    if sys.platform == "win32":
        script = (
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
            "Where-Object { $_.CommandLine -like '*run_maps_job*' } | "
            "Select-Object -ExpandProperty CommandLine"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return addresses_path(job_id).is_file()
        return any(needle in line for line in result.stdout.splitlines())
    try:
        result = subprocess.run(
            ["ps", "-ax", "-o", "command="],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return addresses_path(job_id).is_file()
    return any(needle in line for line in result.stdout.splitlines())


def _kill_job_process(job_id: str) -> None:
    needle = f"run_maps_job {job_id}"
    if sys.platform == "win32":
        script = (
            "$procs = Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
            "Where-Object { $_.CommandLine -like '*run_maps_job*' }; "
            "foreach ($proc in $procs) { "
            f"if ($proc.CommandLine -like '*{job_id}*') {{ Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue }}"
            " }"
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        return

    try:
        result = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        for line in result.stdout.splitlines():
            if needle not in line:
                continue
            pid = line.strip().split(None, 1)[0]
            subprocess.run(["kill", pid], check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _mark_job_interrupted(job_id: str, message: str) -> None:
    update_job(job_id, status="failed", message=message)


def _cleanup_stale_jobs() -> None:
    global _active_job_id

    for job_id in _list_job_ids_with_statuses(ACTIVE_STATUSES):
        if _job_process_running(job_id):
            continue
        _mark_job_interrupted(
            job_id,
            "Automação interrompida (processo encerrado). Inicie novamente.",
        )
        if _active_job_id == job_id:
            _active_job_id = None


def _release_job(job_id: str) -> None:
    global _active_job_id

    update_job(
        job_id,
        cancel_requested=True,
        status="cancelled",
        message="Automação substituída por uma nova execução.",
    )
    _kill_job_process(job_id)
    addresses_path(job_id).unlink(missing_ok=True)
    if _active_job_id == job_id:
        _active_job_id = None


def _sync_active_job_id() -> None:
    global _active_job_id

    _refresh_active_job()
    if _active_job_id:
        return

    active_ids = _list_job_ids_with_statuses(ACTIVE_STATUSES)
    for job_id in active_ids:
        if _job_process_running(job_id):
            _active_job_id = job_id
            return


def _wait_for_job_process_exit(job_id: str, timeout: float = 25.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _job_process_running(job_id):
            return True
        time.sleep(0.5)
    return not _job_process_running(job_id)


def _cleanup_orphan_processes() -> None:
    jobs_dir = _jobs_dir()
    if not jobs_dir.is_dir():
        return

    for path in jobs_dir.glob("*.json"):
        if path.name.endswith("-addresses.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        job_id = str(data.get("id") or "")
        if not job_id:
            continue

        if data.get("status") not in ACTIVE_STATUSES and _job_process_running(job_id):
            _kill_job_process(job_id)


def _resolve_active_job_conflict() -> None:
    global _active_job_id

    _cleanup_stale_jobs()
    _cleanup_orphan_processes()
    _sync_active_job_id()

    if not _active_job_id:
        return

    active = read_job(_active_job_id)
    if not active or active.get("status") not in ACTIVE_STATUSES:
        _active_job_id = None
        return

    status = active.get("status")
    if status == "paused":
        _release_job(_active_job_id)
        return

    if not _job_process_running(_active_job_id):
        _mark_job_interrupted(
            _active_job_id,
            "Automação interrompida (processo encerrado). Inicie novamente.",
        )
        _active_job_id = None
        return

    if status == "running":
        _wait_for_job_process_exit(_active_job_id, timeout=25.0)
        active = read_job(_active_job_id) or {}
        if active.get("status") not in ACTIVE_STATUSES:
            _active_job_id = None
            return
        if not _job_process_running(_active_job_id):
            if active.get("status") == "running":
                _mark_job_interrupted(
                    _active_job_id,
                    "Automação interrompida (processo encerrado). Inicie novamente.",
                )
            _active_job_id = None
            return
        if active.get("status") == "paused":
            _release_job(_active_job_id)
            return
        if active.get("status") == "running":
            raise ValueError(
                "Já existe uma automação em andamento. "
                "Aguarde terminar ou clique em Cancelar."
            )


def run_maps_job(job_id: str) -> None:
    addresses_file = addresses_path(job_id)
    addresses = json.loads(addresses_file.read_text(encoding="utf-8"))
    job_data = read_job(job_id) or {}
    resultados_anteriores = job_data.get("resultados_anteriores") or []

    from .maps_automation import search_addresses_on_map

    update_job(job_id, status="running")

    def on_progress(current: int, total: int, address: str) -> None:
        update_job(job_id, current=current, current_address=address)

    def on_status(message: str) -> None:
        update_job(job_id, message=message)

    def on_partial_result(partial: dict[str, Any]) -> None:
        update_job(job_id, result=partial)

    def should_cancel() -> bool:
        data = read_job(job_id) or {}
        return bool(data.get("cancel_requested"))

    def should_resume() -> bool:
        data = read_job(job_id) or {}
        return bool(data.get("resume_requested"))

    def on_pause() -> None:
        update_job(
            job_id,
            status="paused",
            message="Mapa pronto. Edite o mapa e clique em Continuar pesquisa.",
            resume_requested=False,
        )

    try:
        result = search_addresses_on_map(
            addresses,
            on_progress=on_progress,
            on_status=on_status,
            on_partial_result=on_partial_result,
            should_cancel=should_cancel,
            should_resume=should_resume,
            on_pause=on_pause,
            resultados_anteriores=resultados_anteriores,
        )
        if should_cancel():
            update_job(
                job_id,
                status="cancelled",
                message="Automação cancelada pelo usuário.",
                result=result,
            )
        else:
            viaveis = sum(
                1
                for item in result.get("resultados", [])
                if item.get("viabilidade") == "Dentro da mancha" and item.get("status") == "ok"
            )
            total = result.get("total", 0)
            update_job(
                job_id,
                status="completed",
                message=(
                    f"{viaveis} endereço(s) na mancha verde de {total} processado(s)."
                ),
                result=result,
            )
    except ValueError as exc:
        update_job(job_id, status="failed", message=str(exc))
    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            message=f"Erro inesperado ao executar o Playwright: {exc}",
        )
    finally:
        addresses_file.unlink(missing_ok=True)
        global _active_job_id
        if _active_job_id == job_id:
            _active_job_id = None


def create_job(
    addresses: list[dict[str, Any]] | list[str],
    *,
    resultados_anteriores: list[dict[str, Any]] | None = None,
) -> AutomationJob:
    global _active_job_id

    _resolve_active_job_conflict()

    for job_id in _list_job_ids_with_statuses(ACTIVE_STATUSES):
        if job_id == _active_job_id:
            continue
        if _job_process_running(job_id):
            _release_job(job_id)
        else:
            _mark_job_interrupted(
                job_id,
                "Automação interrompida (processo encerrado). Inicie novamente.",
            )

    job_id = uuid.uuid4().hex
    previous_results = list(resultados_anteriores or [])
    write_job(
        job_id,
        {
            "id": job_id,
            "status": "pending",
            "total": len(addresses),
            "current": len(previous_results),
            "current_address": "",
            "message": (
                f"Retomando automação ({len(previous_results)} endereço(s) já processado(s))..."
                if previous_results
                else "Iniciando automação..."
            ),
            "result": (
                {
                    "total": len(addresses),
                    "processados": len(previous_results),
                    "cancelado": False,
                    "resultados": previous_results,
                }
                if previous_results
                else None
            ),
            "cancel_requested": False,
            "resume_requested": False,
            "resultados_anteriores": previous_results,
        },
    )
    addresses_path(job_id).write_text(
        json.dumps(addresses, ensure_ascii=False),
        encoding="utf-8",
    )
    _active_job_id = job_id

    manage_py = Path(settings.BASE_DIR) / "manage.py"
    log_path = Path(settings.BASE_DIR) / "playwright" / "jobs" / f"{job_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")

    popen_kwargs: dict[str, Any] = {
        "cwd": settings.BASE_DIR,
        "stdin": subprocess.DEVNULL,
        "stdout": log_file,
        "stderr": log_file,
    }
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    subprocess.Popen(
        [sys.executable, str(manage_py), "run_maps_job", job_id],
        **popen_kwargs,
    )

    data = read_job(job_id)
    if not data:
        raise RuntimeError("Não foi possível iniciar a automação.")
    return _job_from_data(data)


def get_job(job_id: str) -> AutomationJob | None:
    global _active_job_id

    data = read_job(job_id)
    if not data:
        return None

    if data.get("status") not in ACTIVE_STATUSES and _active_job_id == job_id:
        _active_job_id = None

    return _job_from_data(data)


def cancel_job(job_id: str) -> AutomationJob | None:
    data = read_job(job_id)
    if not data:
        return None
    if data.get("status") in {"completed", "failed", "cancelled"}:
        return _job_from_data(data)
    update_job(job_id, cancel_requested=True)
    data = read_job(job_id)
    return _job_from_data(data) if data else None


def resume_job(job_id: str) -> AutomationJob | None:
    data = read_job(job_id)
    if not data:
        return None
    if data.get("status") not in {"paused", "running"}:
        return _job_from_data(data)
    update_job(
        job_id,
        resume_requested=True,
        status="running",
        message="Retomando pesquisa de endereços...",
    )
    data = read_job(job_id)
    return _job_from_data(data) if data else None
