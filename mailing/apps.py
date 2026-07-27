import json
import os
from pathlib import Path

from django.apps import AppConfig


class MailingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "mailing"

    def ready(self):
        self._materialize_playwright_storage_state()

    def _materialize_playwright_storage_state(self):
        raw_json = os.environ.get("PLAYWRIGHT_STORAGE_STATE_JSON", "").strip()
        if not raw_json:
            return

        from django.conf import settings

        target = getattr(settings, "PLAYWRIGHT_STORAGE_STATE", "")
        if not target:
            target = str(Path(settings.BASE_DIR) / "playwright" / "google-auth.json")

        path = Path(target)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            parsed = json.loads(raw_json)
            path.write_text(json.dumps(parsed), encoding="utf-8")
        except json.JSONDecodeError:
            path.write_text(raw_json, encoding="utf-8")
