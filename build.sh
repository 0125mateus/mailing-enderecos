#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# Playwright só no ambiente local — no Render free fica desabilitado.
if [ -z "${RENDER:-}" ]; then
  pip install -r requirements-local.txt
  python -m playwright install --with-deps chromium
fi

python manage.py collectstatic --noinput
python manage.py migrate --noinput
