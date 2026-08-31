-- 2026-08-30: dev login accounts on databases initialized before GITHUB-80.
--
-- The Android app stopped sending self-signed JWTs (GITHUB-80 / app commit
-- "JWT leeway fix") and now exchanges credentials at POST /api/v1/auth/login
-- as `mobile`/`password`. init.sql seeded that password on fresh volumes only,
-- so older stands had the user with a NULL password and login 401'd — the app
-- fell back to anonymous requests, and on optional-auth endpoints (media
-- listing) that silently hid every private asset.
--
-- Idempotent: inserts the user only when missing. Password hashes are never
-- literals — the hash comes from the DEV_PASSWORD_HASH env var of the postgres
-- container, passed by scripts/apply_migrations.sh as the psql variable
-- dev_hash. An empty/unset variable leaves password_hash untouched (no-op).

INSERT INTO users (id, username, google_id, role, crystal_balance)
VALUES ('00000000-0000-0000-0000-000000000001', 'mobile', 'mobile@mobile.net', 'api', 1000)
ON CONFLICT (id) DO NOTHING;

UPDATE users SET password_hash = :'dev_hash'
WHERE username IN ('mobile', 'api', 'developer') AND :'dev_hash' <> '';
