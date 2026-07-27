#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# Playwright/Chromium só é necessário localmente; no Render o build quebra.
if [ -z "${RENDER:-}" ]; then
  python -m playwright install --with-deps chromium
fi

python manage.py collectstatic --noinput
python manage.py migrate --noinput
