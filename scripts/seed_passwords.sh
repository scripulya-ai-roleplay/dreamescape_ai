#!/usr/bin/env bash
# Seeds account password hashes from the environment so no hash is committed.
#
# Two run modes:
#   1. Sourced by the postgres entrypoint as
#      /docker-entrypoint-initdb.d/zz-seed-passwords.sh on a fresh volume —
#      POSTGRES_USER / POSTGRES_DB / ADMIN_PASSWORD_HASH / DEV_PASSWORD_HASH
#      come from the container env. The zz- prefix makes it run after init.sql.
#   2. Run directly by CI / operators against a reachable server: export
#      PSQL_ARGS (e.g. "-h 127.0.0.1 -U user -d dbname") and PGPASSWORD.
#
# ADMIN_PASSWORD_HASH sets the `admin` account; DEV_PASSWORD_HASH sets the
# `mobile` / `api` / `developer` accounts. Values are argon2 hashes; generate
# one with:
#   python -c "from argon2 import PasswordHasher; print(PasswordHasher().hash('YOUR-PASSWORD'))"
#
# Empty or missing variables are a no-op (accounts keep password_hash NULL),
# which is the intended fail-closed behavior for stands without secrets.

set -euo pipefail

psql ${PSQL_ARGS:--U "$POSTGRES_USER" -d "$POSTGRES_DB"} \
    -v ON_ERROR_STOP=1 \
    -v admin_hash="${ADMIN_PASSWORD_HASH:-}" \
    -v dev_hash="${DEV_PASSWORD_HASH:-}" <<'SQL'
UPDATE users SET password_hash = :'admin_hash'
WHERE username = 'admin' AND :'admin_hash' <> '';
UPDATE users SET password_hash = :'dev_hash'
WHERE username IN ('mobile', 'api', 'developer') AND :'dev_hash' <> '';
SQL
