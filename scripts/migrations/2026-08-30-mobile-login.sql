-- 2026-08-30: dev login accounts on databases initialized before GITHUB-80.
--
-- The Android app stopped sending self-signed JWTs (GITHUB-80 / app commit
-- "JWT leeway fix") and now exchanges credentials at POST /api/v1/auth/login
-- as `mobile`/`password`. init.sql has seeded that password since 2026-07-21,
-- but init.sql only runs on a fresh postgres volume — older stands have the
-- user with a NULL password, so login 401s and the app falls back to
-- anonymous requests. On optional-auth endpoints (media listing) that
-- silently hides every private asset: character galleries come back empty
-- and covers never render, with no error anywhere.
--
-- Idempotent: inserts the user only when missing and overwrites the hash
-- unconditionally (a fixed dev credential, identical to init.sql). The other
-- three seeded accounts get the same treatment so dev credentials work
-- uniformly on legacy stands.

INSERT INTO users (id, username, google_id, role, crystal_balance)
VALUES ('00000000-0000-0000-0000-000000000001', 'mobile', 'mobile@mobile.net', 'api', 1000)
ON CONFLICT (id) DO NOTHING;

UPDATE users SET password_hash = '$argon2id$v=19$m=65536,t=3,p=4$qXUelaeIrpiI270hrsHowQ$G5DMjlQlJYB354uQujZoptA6LKecJ9UBdznlm/1ZOiY'
WHERE username IN ('mobile', 'admin', 'api', 'developer');
