#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f .env ] || { echo 'Нет .env. Сначала: python3 scripts/make_env.py'; exit 1; }
python3 scripts/create_web_env.py
bash scripts/init_web_auth.sh
COMPOSE=(docker compose -f compose.yaml -f compose.web.yaml)
"${COMPOSE[@]}" up --build -d web
"${COMPOSE[@]}" exec -T web python manage.py check
"${COMPOSE[@]}" exec -T web python manage.py seed_demo
printf '\nОткрой: http://127.0.0.1:8001\n'
