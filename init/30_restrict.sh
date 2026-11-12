#!/bin/bash
set -euo pipefail
: "${APP_READER_PASSWORD:?APP_READER_PASSWORD missing}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_pw="$APP_READER_PASSWORD" <<'SQL'
-- Deny access to high-risk schema and executable functions by default.
REVOKE ALL ON SCHEMA mil_core,etl,excel_stage FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA mil_core FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SELECT format('CREATE ROLE registry_reader LOGIN PASSWORD %L', :'app_pw')
  WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='registry_reader') \gexec
GRANT CONNECT ON DATABASE military_lab TO registry_reader;
GRANT USAGE ON SCHEMA registry_api,refdata TO registry_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA registry_api,refdata TO registry_reader;
ALTER ROLE registry_reader SET default_transaction_read_only = on;
SQL
