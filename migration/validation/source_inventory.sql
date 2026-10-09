-- Compare the installed schema directly with the restored 88-column export.
\set ON_ERROR_STOP on
BEGIN;
CREATE TEMP TABLE source_columns (
    table_name text, ordinal_position text, column_name text, data_type text,
    udt_schema text, udt_name text, character_maximum_length text,
    numeric_precision text, numeric_scale text, datetime_precision text,
    is_nullable text, column_default text, is_identity text, identity_generation text,
    identity_start text, identity_increment text, identity_maximum text,
    identity_minimum text, identity_cycle text
);
\copy source_columns FROM '/tmp/hk-source-columns.csv' WITH (FORMAT csv, HEADER true, NULL 'null')
SELECT hk_validation.assert((SELECT count(*) = 88 FROM source_columns), 'complete source column export');
SELECT hk_validation.assert(NOT EXISTS (
    SELECT FROM source_columns AS source LEFT JOIN information_schema.columns AS target
        ON target.table_schema = 'public' AND target.table_name = source.table_name
        AND target.column_name = source.column_name
    WHERE target.column_name IS NULL
        OR target.ordinal_position::text IS DISTINCT FROM source.ordinal_position
        OR target.data_type IS DISTINCT FROM source.data_type
        OR target.udt_schema IS DISTINCT FROM source.udt_schema
        OR target.udt_name IS DISTINCT FROM source.udt_name
        OR target.character_maximum_length::text IS DISTINCT FROM source.character_maximum_length
        OR target.numeric_precision::text IS DISTINCT FROM source.numeric_precision
        OR target.numeric_scale::text IS DISTINCT FROM source.numeric_scale
        OR target.datetime_precision::text IS DISTINCT FROM source.datetime_precision
        OR target.is_identity IS DISTINCT FROM source.is_identity
        OR target.identity_generation IS DISTINCT FROM source.identity_generation
        OR target.identity_start IS DISTINCT FROM source.identity_start
        OR target.identity_increment IS DISTINCT FROM source.identity_increment
        OR target.identity_maximum IS DISTINCT FROM source.identity_maximum
        OR target.identity_minimum IS DISTINCT FROM source.identity_minimum
        OR target.identity_cycle IS DISTINCT FROM source.identity_cycle
        OR target.is_nullable IS DISTINCT FROM CASE
            WHEN source.table_name = 'tulemustepank' AND source.column_name IN
                ('test_id','yp_id','graafi_objekt_snapshot','tyvi_snapshot','voti_snapshot') THEN 'NO'
            WHEN source.table_name = 'yg_tellimused' AND source.column_name = 'maht' THEN 'NO'
            WHEN source.table_name = 'ylesandepank' AND source.column_name = 'ebaadekvaatne_arv' THEN 'NO'
            ELSE source.is_nullable END
        OR target.column_default IS DISTINCT FROM CASE
            WHEN source.column_default = 'timezone(''utc''::text, now())' THEN 'now()'
            ELSE source.column_default END
), 'exact source types/order/identity/defaults/nullability with only approved changes');
SELECT hk_validation.assert((SELECT array_agg(column_name::text ORDER BY ordinal_position) =
    ARRAY['attempt_count','next_attempt_at','locked_until','claim_token','last_error','completed_at']
    FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'yg_tellimused'
        AND ordinal_position > 11), 'exact six new worker columns');
ROLLBACK;
