-- 2026-08-31: rotate seeded account credentials off the previously committed
-- hash.
--
-- The argon2 hash for password "password" was hardcoded in init.sql and an
-- earlier revision of 2026-08-30-mobile-login.sql, i.e. public to anyone with
-- repository read access, and applied to admin/api/developer/mobile on every
-- database the applier touched. This migration replaces those hashes with
-- values supplied through the postgres container environment:
--
--   ADMIN_PASSWORD_HASH — argon2 hash for the `admin` account
--   DEV_PASSWORD_HASH   — argon2 hash for `mobile` / `api` / `developer`
--
-- (passed by scripts/apply_migrations.sh as psql variables admin_hash /
-- dev_hash).
--
-- Fail-closed on empty variables: the applier records this file in
-- schema_migrations on its first run no matter what the UPDATEs do, so a
-- silent no-op would pin the four accounts to the leaked hash forever (later
-- re-runs with the variables finally set just report "already applied").
-- These are seeded accounts — the environment is the source of truth for
-- their credentials — so an empty variable sets password_hash back to NULL:
-- login then 401s, the documented password-less behavior, instead of the
-- leaked hash surviving. To set a password after this file has been applied
-- with an empty variable, re-seed on a fresh volume (dev) or UPDATE by hand
-- with a hash from the argon2 snippet (prod) — the ledger already considers
-- this file done. The final SELECT prints the per-account outcome so a
-- passwordless result is visible in the migration log.

UPDATE users SET password_hash = :'admin_hash'
WHERE username = 'admin' AND :'admin_hash' <> '';

UPDATE users SET password_hash = NULL
WHERE username = 'admin' AND :'admin_hash' = '' AND password_hash IS NOT NULL;

UPDATE users SET password_hash = :'dev_hash'
WHERE username IN ('mobile', 'api', 'developer') AND :'dev_hash' <> '';

UPDATE users SET password_hash = NULL
WHERE username IN ('mobile', 'api', 'developer') AND :'dev_hash' = '' AND password_hash IS NOT NULL;

SELECT username,
       CASE WHEN password_hash IS NULL
            THEN 'PASSWORDLESS — empty hash variable, login will 401 (fail-closed)'
            ELSE 'password set from environment' END AS outcome
FROM users
WHERE username IN ('admin', 'mobile', 'api', 'developer')
ORDER BY username;
