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
#   scripts/apply_migrations.sh <postgres-container> --redo=<filename.sql>
#
# --dry-run lists what would be applied (and still creates the ledger table —
# it is harmless metadata) without executing any migration file.
# --redo=<filename> re-applies one already-ledgered file (its ledger row is
# deleted first). Escape hatch for the container-env prerequisite below: a
# fail-closed password migration applied while the hashes were unset NULLed
# the accounts and got ledgered; --redo re-runs it once the container carries
# the hashes.
#
# Environment (read inside the container):
#   POSTGRES_USER / POSTGRES_DB — standard postgres image vars; the container
#   has them set, so credentials never appear in this script or in CI logs.
#   ADMIN_PASSWORD_HASH / DEV_PASSWORD_HASH — optional argon2 hashes handed to
#   migrations as the psql variables admin_hash / dev_hash (referenced in SQL
#   as :'admin_hash' / :'dev_hash'). PREREQUISITE: docker exec only sees the
#   container's CREATION-TIME env — env_file values injected by a compose
#   change land in the container after it is RECREATED, not after a restart.
#   On a stand whose postgres container predates the env change, these are
#   empty here; a fail-closed migration then NULLs the seeded passwords and
#   still gets ledgered (re-runs report "already applied"). Recreate the
#   container first (docker compose up -d postgres) or use --redo after it.
#   Hash values never appear in this script or in logs.
#
# Exits non-zero on the first failure; each file runs statement-by-statement in
# psql autocommit, so a mid-file failure leaves earlier statements applied —
# which is exactly why files must be idempotent (re-run resumes safely).

set -euo pipefail

# Empty string = real run; "true" = dry run. The `${DRY_RUN:+…}` expansions
# below rely on empty-vs-non-empty, so don't set this to "false".
DRY_RUN=""
REDO=""
CONTAINER=""
MIGRATIONS_DIR=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --redo=*) REDO="${arg#--redo=}" ;;
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
usage() { echo "usage: apply_migrations.sh <postgres-container> [migrations-dir] [--dry-run] [--redo=<filename.sql>]" >&2; }
[ -n "$CONTAINER" ] || { usage; exit 1; }
MIGRATIONS_DIR="${MIGRATIONS_DIR:-$(cd "$(dirname "$0")" && pwd)/migrations}"
[ -n "$REDO" ] && [ -e "$MIGRATIONS_DIR/$REDO" ] || { [ -z "$REDO" ] || { echo "!! --redo file not found in $MIGRATIONS_DIR: $REDO" >&2; exit 1; }; }

[ -d "$MIGRATIONS_DIR" ] || { echo "!! migrations dir not found: $MIGRATIONS_DIR" >&2; exit 1; }

# psql invocation inside the container (uses the container's own env for
# user/db so this works identically on the dev stand and the VPS). $PSQL is
# spliced into an `sh -c "..."` argument, so variable NAMES must cross the
# outer shell and let the inner shell expand them once from the container env.
# Expanding a value at the outer level instead would splice an argon2 hash
# (`$argon2id$v=19$m=...`) into a command string the inner shell parses inside
# double quotes — its dollars would be expanded away and the hash destroyed.
PSQL='psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'

echo "==> Creating schema_migrations ledger if missing"
docker exec -i "$CONTAINER" sh -c "$PSQL -q" <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
SQL

echo "==> Applying migrations from $MIGRATIONS_DIR to $CONTAINER${DRY_RUN:+ (dry run)}${REDO:+ (redo $REDO)}"
applied=0
skipped=0

if [ -n "$REDO" ]; then
    echo "==> --redo: deleting ledger row for $REDO"
    docker exec "$CONTAINER" sh -c \
        "$PSQL -q -c \"DELETE FROM schema_migrations WHERE filename = '$REDO'\""
fi

for file in "$MIGRATIONS_DIR"/*.sql; do
    [ -e "$file" ] || { echo "!! no .sql files in $MIGRATIONS_DIR" >&2; exit 1; }
    name=$(basename "$file")
    [ -z "$REDO" ] || [ "$name" = "$REDO" ] || continue

    already=$(docker exec "$CONTAINER" sh -c \
        "$PSQL -tA -c \"SELECT count(*) FROM schema_migrations WHERE filename = '$name'\"")
    if [ "$already" != "0" ]; then
        echo "    skip  $name (already applied)"
        skipped=$((skipped + 1))
        continue
    fi

    if [ -z "$DRY_RUN" ] && grep -q "admin_hash\|dev_hash" "$file"; then
        container_admin=$(docker exec "$CONTAINER" sh -c '[ -n "$ADMIN_PASSWORD_HASH" ] && echo set || echo empty')
        container_dev=$(docker exec "$CONTAINER" sh -c '[ -n "$DEV_PASSWORD_HASH" ] && echo set || echo empty')
        if [ "$container_admin" = "empty" ] || [ "$container_dev" = "empty" ]; then
            echo "    !! WARNING $name reads admin_hash/dev_hash from the CONTAINER env," >&2
            echo "    !! but the container was created without at least one of ADMIN_PASSWORD_HASH/" >&2
            echo "    !! DEV_PASSWORD_HASH — docker exec only sees creation-time env." >&2
            echo "    !! A fail-closed migration will NULL those seeded passwords (and still" >&2
            echo "    !! be ledgered). Recreate the container first: docker compose up -d" >&2
            echo "    !! postgres; if it is too late, re-apply with --redo=$name afterwards." >&2
        fi
    fi

    if [ -n "$DRY_RUN" ]; then
        echo "    would apply $name"
        applied=$((applied + 1))
        continue
    fi

    echo "    apply $name"
    docker exec -i "$CONTAINER" sh -c \
        "$PSQL -q -v admin_hash=\"\$ADMIN_PASSWORD_HASH\" -v dev_hash=\"\$DEV_PASSWORD_HASH\"" < "$file"

    docker exec "$CONTAINER" sh -c \
        "$PSQL -q -c \"INSERT INTO schema_migrations (filename) VALUES ('$name') ON CONFLICT (filename) DO NOTHING\""
    applied=$((applied + 1))
done

echo "==> Done: $applied ${DRY_RUN:+would be }applied, $skipped skipped"
