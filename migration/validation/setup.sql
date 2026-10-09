-- Synthetic acceptance database only. Never run on production.
\set ON_ERROR_STOP on
CREATE SCHEMA hk_validation;
CREATE FUNCTION hk_validation.assert(ok boolean, label text)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
    IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'Assertion failed: %', label; END IF;
END;
$$;
CREATE FUNCTION hk_validation.expect_error(statement text, expected_state text)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
BEGIN
    BEGIN
        EXECUTE statement;
    EXCEPTION WHEN OTHERS THEN
        IF SQLSTATE = expected_state THEN RETURN; END IF;
        RAISE EXCEPTION 'Expected %, got %: % (SQL: %)', expected_state, SQLSTATE, SQLERRM, statement;
    END;
    RAISE EXCEPTION 'Expected % but statement succeeded: %', expected_state, statement;
END;
$$;
GRANT USAGE ON SCHEMA hk_validation TO hindamiskomponent_owner,
    hindamiskomponent_app, hindamiskomponent_admin, hindamiskomponent_worker;

BEGIN;
SET LOCAL ROLE hindamiskomponent_owner;
INSERT INTO public.graafid_kst (graaf_hash, graafi_struktuur, teadmusruum_maatriks)
VALUES ('fixture-graph', '{"nodes":["node"],"relations":[]}', '[[0],[1]]');
INSERT INTO public.kst_configuration_versions
    (id, schema_version, configuration, configuration_hash, created_by)
VALUES ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 1, '{"schema_version":1}',
    'kst-config-v1:sha256:' || repeat('a', 64), 'schema-fixture');
INSERT INTO public.kst_configuration_activations (configuration_version_id, activated_by)
VALUES ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'schema-fixture');
INSERT INTO public.kst_model_cache (graph_hash, configuration_hash, model_schema_version, model_payload)
VALUES ('fixture-graph', 'kst-config-v1:sha256:' || repeat('a', 64), 2,
    jsonb_build_object('schema_version', 2, 'method', 'kst',
        'configuration_hash', 'kst-config-v1:sha256:' || repeat('a', 64)));
INSERT INTO public.repo_materjalid (kursus, sisu_tekst) VALUES ('course', 'source');
INSERT INTO public.yg_reeglid (kursus, reegli_kirjeldus, naidis_json) VALUES ('course', 'rule', '{}');
INSERT INTO public.ylesandepank (kursus, graafi_objekt, graafi_ema_objekt, tyvi,
    voti, distraktor_1, distraktor_2, distraktor_3, staatus)
SELECT 'course', 'node', 'parent', 'original prompt ' || n, 'correct', 'one', 'two', 'three', 'kasutatav'
FROM generate_series(1, 3) AS n;
INSERT INTO public.testisessioonid (test_id, kasutaja_id, rada_id, graaf_hash, staatus, tp_seisund)
VALUES ('test-a', 'learner-a', 'path-a', 'fixture-graph', 'aktiivne',
    '{"schema_version":2,"current_question":{"item_id":1,"submission_id":"11111111-1111-1111-1111-111111111111"}}'),
    ('test-b', 'learner-b', 'path-b', 'fixture-graph', 'aktiivne',
    '{"schema_version":2,"current_question":{"item_id":2,"submission_id":"22222222-2222-2222-2222-222222222222"}}');
-- Two historical answers to the same item/test are intentional.
INSERT INTO public.tulemustepank (test_id, yp_id, skoor, valitud_vastus,
    graafi_objekt_snapshot, tyvi_snapshot, voti_snapshot)
VALUES ('test-a', 2, 1, 'correct', 'node', 'saved prompt', 'correct'),
       ('test-a', 2, 0, 'one', 'node', 'saved prompt', 'correct'),
       ('test-b', 2, 1, 'correct', 'node', 'saved prompt', 'correct');
INSERT INTO public.yg_tellimused (test_id, kursus, graafi_objektid, staatus,
    next_attempt_at, locked_until, claim_token)
VALUES ('test-a', 'course', '["node"]', 'ootel', NULL, NULL, NULL),
       ('test-a', 'course', '["node"]', 'ootel', now() + interval '1 day', NULL, NULL),
       ('test-b', 'course', '["node"]', 'tootmises', NULL, now() - interval '1 day', '33333333-3333-3333-3333-333333333333'),
       ('test-b', 'course', '["node"]', 'tootmises', NULL, now() + interval '1 day', gen_random_uuid()),
       ('test-a', 'course', '["node"]', 'tehtud', NULL, NULL, NULL),
       ('test-b', 'course', '["node"]', 'viga', NULL, NULL, NULL),
       ('test-a', 'course', '["node"]', 'ootel', now() - interval '1 day', NULL, NULL),
       ('no-session', 'course', '["node"]', 'ootel', NULL, NULL, NULL);
COMMIT;
