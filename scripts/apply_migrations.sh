#!/usr/bin/env bash
# Applies pending SQL migrations from scripts/migrations/ to the Postgres
# database inside a running docker container.
#
# Each applied file is recorded in the schema_migrations ledger table; a file
# that already has a row is skipped, so re-running this script is a no-op.
# Files must still be idempotent on their own (IF NOT EXISTS etc.) — the ledger
# guards ordering and accidental skips, not a partially-applied file.
#
# Usage:
#   scripts/apply_migrations.sh <postgres-container> [migrations-dir] [--dry-run]
#
# --dry-run lists what would be applied (and still creates the ledger table —
# it is harmless metadata) without executing any migration file.
#
# Environment (read inside the container):
#   POSTGRES_USER / POSTGRES_DB — standard postgres image vars; the container
#   has them set, so credentials never appear in this script or in CI logs.
#
# Exits non-zero on the first failure; each file runs statement-by-statement in
# psql autocommit, so a mid-file failure leaves earlier statements applied —
# which is exactly why files must be idempotent (re-run resumes safely).

set -euo pipefail

# Empty string = real run; "true" = dry run. The `${DRY_RUN:+…}` expansions
# below rely on empty-vs-non-empty, so don't set this to "false".
DRY_RUN=""
CONTAINER=""
MIGRATIONS_DIR=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        -*) echo "!! unknown flag: $arg" >&2; exit 1 ;;
        *)
            if [ -z "$CONTAINER" ]; then
                CONTAINER="$arg"
            elif [ -z "$MIGRATIONS_DIR" ]; then
                MIGRATIONS_DIR="$arg"
            else
                echo "!! unexpected argument: $arg" >&2; exit 1
            fi
            ;;
    esac
done
[ -n "$CONTAINER" ] || { echo "usage: apply_migrations.sh <postgres-container> [migrations-dir] [--dry-run]" >&2; exit 1; }
MIGRATIONS_DIR="${MIGRATIONS_DIR:-$(cd "$(dirname "$0")" && pwd)/migrations}"

[ -d "$MIGRATIONS_DIR" ] || { echo "!! migrations dir not found: $MIGRATIONS_DIR" >&2; exit 1; }

# psql invocation inside the container (uses the container's own env for
# user/db so this works identically on the dev stand and the VPS).
PSQL="psql -U \$POSTGRES_USER -d \$POSTGRES_DB -v ON_ERROR_STOP=1"

echo "==> Creating schema_migrations ledger if missing"
docker exec -i "$CONTAINER" sh -c "$PSQL -q" <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
SQL

echo "==> Applying migrations from $MIGRATIONS_DIR to $CONTAINER${DRY_RUN:+ (dry run)}"
applied=0
skipped=0

for file in "$MIGRATIONS_DIR"/*.sql; do
    [ -e "$file" ] || { echo "!! no .sql files in $MIGRATIONS_DIR" >&2; exit 1; }
    name=$(basename "$file")

    already=$(docker exec "$CONTAINER" sh -c \
        "$PSQL -tA -c \"SELECT count(*) FROM schema_migrations WHERE filename = '$name'\"")
    if [ "$already" != "0" ]; then
        echo "    skip  $name (already applied)"
        skipped=$((skipped + 1))
        continue
    fi

    if [ -n "$DRY_RUN" ]; then
        echo "    would apply $name"
        applied=$((applied + 1))
        continue
    fi

    echo "    apply $name"
    docker exec -i "$CONTAINER" sh -c "$PSQL -q" < "$file"

    docker exec "$CONTAINER" sh -c \
        "$PSQL -q -c \"INSERT INTO schema_migrations (filename) VALUES ('$name')\""
    applied=$((applied + 1))
done

echo "==> Done: $applied ${DRY_RUN:+would be }applied, $skipped skipped"
