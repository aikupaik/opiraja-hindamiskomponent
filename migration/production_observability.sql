-- Run once as the provisioning DBA in hindamiskomponent, before the V1 DDL.
-- Configure shared_preload_libraries = 'pg_stat_statements' (preserving any
-- other libraries) and restart PostgreSQL before using its statistics views.
-- This does not create roles, set passwords, or change server configuration.
\set ON_ERROR_STOP on
BEGIN;
DO $preflight$
BEGIN
    IF current_database() <> 'hindamiskomponent' THEN
        RAISE EXCEPTION 'Expected database hindamiskomponent';
    END IF;
END;
$preflight$;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
COMMIT;
