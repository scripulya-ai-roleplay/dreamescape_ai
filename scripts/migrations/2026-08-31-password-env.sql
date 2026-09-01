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
-- dev_hash). The UPDATEs are unconditional per account when the variable is
-- non-empty, which is what rotates databases that already carry the leaked
-- hash; empty/unset variables are a safe no-op.

UPDATE users SET password_hash = :'admin_hash'
WHERE username = 'admin' AND :'admin_hash' <> '';

UPDATE users SET password_hash = :'dev_hash'
WHERE username IN ('mobile', 'api', 'developer') AND :'dev_hash' <> '';
