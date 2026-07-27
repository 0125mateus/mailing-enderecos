#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

if [ -n "${RENDER:-}" ]; then
  export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-${PWD}/.playwright-browsers}"
  python -m playwright install chromium
  python -m playwright install-deps chromium
else
  python -m playwright install --with-deps chromium
fi

python manage.py collectstatic --noinput
python manage.py migrate --noinput
