#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# Playwright: sempre no PC local; no Render quando PLAYWRIGHT_ENABLED=True (plano Pro).
if [ -z "${RENDER:-}" ] || [ "${PLAYWRIGHT_ENABLED:-False}" = "True" ]; then
  pip install -r requirements-local.txt
  python -m playwright install --with-deps chromium
fi

python manage.py collectstatic --noinput
python manage.py migrate --noinput
