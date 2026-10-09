\set ON_ERROR_STOP on
BEGIN;
SET LOCAL ROLE hindamiskomponent_owner;
SELECT hk_validation.assert((SELECT count(*) = 10 FROM pg_catalog.pg_class
    WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'
      AND relrowsecurity AND relforcerowsecurity AND relowner = current_user::regrole), 'ten owner tables force RLS');
SELECT hk_validation.assert((SELECT count(*) = 94 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name IN (
        'graafid_kst','kst_configuration_versions','kst_configuration_activations','kst_model_cache',
        'repo_materjalid','testisessioonid','tulemustepank','yg_reeglid','yg_tellimused','ylesandepank')), '88 source columns plus six worker columns');
SELECT hk_validation.assert((SELECT count(*) = 15 FROM pg_catalog.pg_indexes
    WHERE schemaname = 'public'), 'PK/unique indexes plus exactly three query indexes');
SELECT hk_validation.assert((SELECT count(*) = 6 AND bool_and(seqstart = 1 AND seqincrement = 1
    AND seqmin = 1 AND seqmax = 9223372036854775807 AND seqcache = 1 AND NOT seqcycle)
    FROM pg_catalog.pg_sequence WHERE seqrelid IN (SELECT oid FROM pg_catalog.pg_class
        WHERE relnamespace = 'public'::regnamespace)), 'identity sequence options');
SELECT hk_validation.assert((SELECT count(*) = 6 AND bool_and(confdeltype = 'r')
    FROM pg_catalog.pg_constraint WHERE contype = 'f' AND connamespace = 'public'::regnamespace), 'six restrictive FKs');
SELECT hk_validation.assert((SELECT count(*) = 6 AND bool_and(confupdtype = CASE
    WHEN conname LIKE 'kst_%' THEN 'r'::"char" ELSE 'a'::"char" END)
    FROM pg_catalog.pg_constraint WHERE contype = 'f' AND connamespace = 'public'::regnamespace), 'source FK update actions preserved');
SELECT hk_validation.assert((SELECT count(*) = 6 FROM pg_catalog.pg_trigger
    WHERE NOT tgisinternal AND tgrelid IN (SELECT oid FROM pg_catalog.pg_class
        WHERE relnamespace = 'public'::regnamespace)), 'five immutable tables and item operation guard; no webhook');
SELECT hk_validation.assert((SELECT count(*) = 2 FROM public.tulemustepank
    WHERE test_id = 'test-a' AND yp_id = 2), 'repeat answers allowed');

DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['graafid_kst','kst_configuration_versions','kst_configuration_activations','kst_model_cache','tulemustepank'] LOOP
        PERFORM hk_validation.expect_error(format('UPDATE public.%I SET %I = %I', tab,
            CASE tab WHEN 'graafid_kst' THEN 'graaf_hash' WHEN 'kst_model_cache' THEN 'graph_hash'
                WHEN 'kst_configuration_activations' THEN 'activated_by' ELSE 'id' END,
            CASE tab WHEN 'graafid_kst' THEN 'graaf_hash' WHEN 'kst_model_cache' THEN 'graph_hash'
                WHEN 'kst_configuration_activations' THEN 'activated_by' ELSE 'id' END), 'P0001');
        PERFORM hk_validation.expect_error(format('DELETE FROM public.%I', tab), 'P0001');
    END LOOP;
END;
$$;
SELECT hk_validation.expect_error($sql$DELETE FROM public.testisessioonid WHERE test_id = 'test-a'$sql$, '23503');
SELECT hk_validation.expect_error($sql$DELETE FROM public.ylesandepank WHERE yp_id = 2$sql$, '23503');
SELECT hk_validation.expect_error($sql$INSERT INTO public.kst_configuration_versions
    (schema_version, configuration, configuration_hash, created_by)
    VALUES (1, '{}', 'kst-config-v1:sha256:' || repeat('b',64), 'fixture')$sql$, '23514');
SELECT hk_validation.expect_error($sql$INSERT INTO public.kst_configuration_versions
    (schema_version, configuration, configuration_hash, created_by)
    VALUES (1, '{"schema_version":null}', 'kst-config-v1:sha256:' || repeat('b',64), 'fixture')$sql$, '23514');
SELECT hk_validation.expect_error($sql$INSERT INTO public.kst_model_cache
    (graph_hash, configuration_hash, model_schema_version, model_payload)
    VALUES ('fixture-graph', 'kst-config-v1:sha256:' || repeat('a',64), 2, '{}')$sql$, '23514');
SELECT hk_validation.expect_error($sql$INSERT INTO public.kst_model_cache
    (graph_hash, configuration_hash, model_schema_version, model_payload)
    VALUES ('fixture-graph', 'kst-config-v1:sha256:' || repeat('a',64), 2,
    jsonb_build_object('schema_version', null, 'method','kst', 'configuration_hash', 'kst-config-v1:sha256:' || repeat('a',64)))$sql$, '23514');
SELECT hk_validation.expect_error($sql$INSERT INTO public.kst_model_cache
    (graph_hash, configuration_hash, model_schema_version, model_payload)
    VALUES ('fixture-graph', 'kst-config-v1:sha256:' || repeat('a',64), 2,
    jsonb_build_object('schema_version', 2, 'method',null, 'configuration_hash', 'kst-config-v1:sha256:' || repeat('a',64)))$sql$, '23514');
SELECT hk_validation.expect_error($sql$INSERT INTO public.kst_model_cache
    (graph_hash, configuration_hash, model_schema_version, model_payload)
    VALUES ('fixture-graph', 'kst-config-v1:sha256:' || repeat('a',64), 2,
    '{"schema_version":2,"method":"kst","configuration_hash":null}')$sql$, '23514');
SELECT hk_validation.expect_error($sql$INSERT INTO public.tulemustepank
    (test_id,yp_id,skoor,valitud_vastus,graafi_objekt_snapshot,voti_snapshot)
    VALUES ('test-a',1,1,'correct','node','correct')$sql$, '23502');
SELECT hk_validation.expect_error($sql$INSERT INTO public.tulemustepank
    (test_id,yp_id,skoor,valitud_vastus,tyvi_snapshot,voti_snapshot)
    VALUES ('test-a',1,1,'correct','prompt','correct')$sql$, '23502');
SELECT hk_validation.expect_error($sql$INSERT INTO public.tulemustepank
    (test_id,yp_id,skoor,valitud_vastus,graafi_objekt_snapshot,tyvi_snapshot)
    VALUES ('test-a',1,1,'correct','node','prompt')$sql$, '23502');
SELECT hk_validation.expect_error($sql$INSERT INTO public.tulemustepank
    (yp_id,skoor,valitud_vastus,graafi_objekt_snapshot,tyvi_snapshot,voti_snapshot)
    VALUES (1,1,'correct','node','prompt','correct')$sql$, '23502');
SELECT hk_validation.expect_error($sql$INSERT INTO public.tulemustepank
    (test_id,skoor,valitud_vastus,graafi_objekt_snapshot,tyvi_snapshot,voti_snapshot)
    VALUES ('test-a',1,'correct','node','prompt','correct')$sql$, '23502');
SELECT hk_validation.expect_error($sql$UPDATE public.yg_tellimused SET maht = 0 WHERE id = 1$sql$, '23514');
SELECT hk_validation.expect_error($sql$UPDATE public.yg_tellimused SET attempt_count = -1 WHERE id = 1$sql$, '23514');
SELECT hk_validation.expect_error($sql$UPDATE public.ylesandepank SET ebaadekvaatne_arv = -1 WHERE yp_id = 1$sql$, '23514');

DO $$
DECLARE runtime_name text; tab text;
BEGIN
    FOREACH runtime_name IN ARRAY ARRAY['hindamiskomponent_app','hindamiskomponent_admin','hindamiskomponent_worker'] LOOP
        PERFORM hk_validation.assert(NOT has_schema_privilege(runtime_name,'public','CREATE')
            AND NOT has_database_privilege(runtime_name,current_database(),'CREATE')
            AND NOT has_database_privilege(runtime_name,current_database(),'TEMP'), 'runtime has no DDL privileges');
        FOREACH tab IN ARRAY ARRAY['graafid_kst','kst_configuration_versions','kst_configuration_activations','kst_model_cache',
            'repo_materjalid','testisessioonid','tulemustepank','yg_reeglid','yg_tellimused','ylesandepank'] LOOP
            PERFORM hk_validation.assert(NOT has_table_privilege(runtime_name,'public.' || tab,'UPDATE')
                AND NOT has_table_privilege(runtime_name,'public.' || tab,'DELETE')
                AND NOT has_table_privilege(runtime_name,'public.' || tab,'TRUNCATE'), 'runtime lacks broad update/delete/truncate');
        END LOOP;
    END LOOP;
END;
$$;
-- New objects must not inherit the old blanket runtime grants.
CREATE TABLE public.validation_default_privileges (id integer);
CREATE FUNCTION public.validation_default_execute() RETURNS integer LANGUAGE sql AS 'SELECT 1';
SELECT hk_validation.assert(NOT has_table_privilege('hindamiskomponent_app','public.validation_default_privileges','SELECT')
    AND NOT has_function_privilege('hindamiskomponent_app','public.validation_default_execute()','EXECUTE'), 'safe future defaults');
ROLLBACK;
