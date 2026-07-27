#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
python -m playwright install --with-deps chromium
python manage.py collectstatic --noinput
python manage.py migrate --noinput
