-- Database roles (docs/ARCHITECTURE.md §8.2).
-- Run once per environment. Locally docker-compose runs it automatically;
-- on Neon/Supabase run it by hand in the SQL console (change the passwords!).
--
--   app_owner : owns the schema, runs Alembic migrations. RLS is bypassed for the owner.
--   app_rw    : used by the running API. Not the owner, so row-level security applies.
--   app_purge : used only by the retention job; the only role allowed to DELETE history tables.

CREATE ROLE app_owner LOGIN PASSWORD 'app_owner';
CREATE ROLE app_rw    LOGIN PASSWORD 'app_rw';
CREATE ROLE app_purge LOGIN PASSWORD 'app_purge';

GRANT ALL ON DATABASE wa_platform TO app_owner;
GRANT CONNECT ON DATABASE wa_platform TO app_rw, app_purge;

\connect wa_platform

ALTER SCHEMA public OWNER TO app_owner;
GRANT USAGE ON SCHEMA public TO app_rw, app_purge;

-- Every table app_owner creates is readable/writable by app_rw and app_purge.
-- Append-only tables REVOKE UPDATE, DELETE from app_rw in their own migration.
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw, app_purge;
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO app_rw, app_purge;
