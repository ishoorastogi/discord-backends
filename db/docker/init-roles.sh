#!/usr/bin/env bash

set -euo pipefail

echo "[INFO] Initializing PostgreSQL roles..."

: "${ADMIN_PASSWORD:?ADMIN_PASSWORD is required}"
: "${BROTHERHOOD_BOT_PASSWORD:?BROTHERHOOD_BOT_PASSWORD is required}"
: "${FINANCE_USER_PASSWORD:?FINANCE_USER_PASSWORD is required}"

psql \
    -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    -v admin_password="$ADMIN_PASSWORD" \
    -v brotherhood_password="$BROTHERHOOD_BOT_PASSWORD" \
    -v finance_password="$FINANCE_USER_PASSWORD" <<'SQL'

-- Administrator
SELECT format(
    'CREATE ROLE admin WITH LOGIN SUPERUSER PASSWORD %L',
    :'admin_password'
)
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'admin'
)
\gexec

-- Brotherhood backend
SELECT format(
    'CREATE ROLE brotherhood_bot WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L',
    :'brotherhood_password'
)
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'brotherhood_bot'
)
\gexec

-- Finance service
SELECT format(
    'CREATE ROLE finance_user WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD %L',
    :'finance_password'
)
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = 'finance_user'
)
\gexec

SQL

echo "[INFO] PostgreSQL roles initialized."