#!/usr/bin/env bash
# Creates a disposable, network-isolated PostgreSQL 16 database. No live DB URL.
set -euo pipefail
schema_dir=$(cd "$(dirname "$0")" && pwd)
validation_container="hk-schema-v1-validation-$$"
validation_image=${HK_VALIDATION_IMAGE:-postgres:16-alpine}
cleanup() { docker rm -f "$validation_container" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker run --detach --rm --name "$validation_container" --network none \
    --env POSTGRES_HOST_AUTH_METHOD=trust --env POSTGRES_DB=hindamiskomponent \
    "$validation_image" -c shared_preload_libraries=pg_stat_statements >/dev/null
for attempt in {1..30}; do
    if docker exec "$validation_container" pg_isready -U postgres -d hindamiskomponent >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
docker exec -i "$validation_container" psql -X -q -v ON_ERROR_STOP=1 -U postgres -d hindamiskomponent <<'SQL'
CREATE ROLE hindamiskomponent_owner NOLOGIN;
CREATE ROLE hindamiskomponent_migrator LOGIN NOINHERIT;
CREATE ROLE hindamiskomponent_app LOGIN;
CREATE ROLE hindamiskomponent_admin LOGIN;
CREATE ROLE hindamiskomponent_worker LOGIN;
GRANT hindamiskomponent_owner TO hindamiskomponent_migrator;
ALTER DATABASE hindamiskomponent OWNER TO hindamiskomponent_owner;
-- Simulate the existing unsafe owner defaults; the DDL must remove them.
ALTER DEFAULT PRIVILEGES FOR ROLE hindamiskomponent_owner GRANT ALL ON TABLES TO hindamiskomponent_app;
ALTER DEFAULT PRIVILEGES FOR ROLE hindamiskomponent_owner IN SCHEMA public GRANT ALL ON TABLES TO hindamiskomponent_admin;
ALTER DEFAULT PRIVILEGES FOR ROLE hindamiskomponent_owner GRANT ALL ON SEQUENCES TO hindamiskomponent_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE hindamiskomponent_owner IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO hindamiskomponent_worker;
SQL
docker exec -i "$validation_container" psql -X -q -U postgres -d hindamiskomponent < "$schema_dir/production_observability.sql"
docker exec -i "$validation_container" psql -X -q -U hindamiskomponent_migrator -d hindamiskomponent < "$schema_dir/production_schema_v1.sql"
docker exec -i "$validation_container" psql -X -q -U postgres -d hindamiskomponent < "$schema_dir/validation/setup.sql"
docker cp "$schema_dir/review_queries_1.csv" "$validation_container:/tmp/hk-source-columns.csv" >/dev/null
docker exec -i "$validation_container" psql -X -q -U postgres -d hindamiskomponent < "$schema_dir/validation/source_inventory.sql"
docker exec -i "$validation_container" psql -X -q -U hindamiskomponent_migrator -d hindamiskomponent < "$schema_dir/validation/owner.sql"
for validation_role in app admin worker; do
    docker exec -i "$validation_container" psql -X -q -U "hindamiskomponent_$validation_role" \
        -d hindamiskomponent < "$schema_dir/validation/$validation_role.sql"
done
printf 'PostgreSQL 16 schema, owner, app, admin and worker checks passed.\n'
