import json
import time
from pathlib import Path
from typing import Any

from django.conf import settings


def _jobs_dir() -> Path:
    directory = Path(settings.BASE_DIR) / "playwright" / "jobs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def job_path(job_id: str) -> Path:
    return _jobs_dir() / f"{job_id}.json"


def addresses_path(job_id: str) -> Path:
    return _jobs_dir() / f"{job_id}-addresses.json"


def write_job(job_id: str, data: dict[str, Any]) -> None:
    path = job_path(job_id)
    temp_path = path.with_suffix(".json.tmp")
    payload = json.dumps(data, ensure_ascii=False)
    temp_path.write_text(payload, encoding="utf-8")
    temp_path.replace(path)


def read_job(job_id: str, *, retries: int = 8) -> dict[str, Any] | None:
    path = job_path(job_id)
    if not path.is_file():
        return None

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                raise json.JSONDecodeError("empty job file", text, 0)
            return json.loads(text)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(0.04 * (attempt + 1))
                continue
            break

    if last_error:
        return None
    return None


def update_job(job_id: str, **fields: Any) -> dict[str, Any]:
    data = read_job(job_id) or {"id": job_id}
    data.update(fields)
    write_job(job_id, data)
    return data
