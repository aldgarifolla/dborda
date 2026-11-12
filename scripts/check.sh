#!/bin/sh
set -eu
docker compose exec -T db psql -U postgres -d military_lab -f /dev/stdin < scripts/validate.sql
