\set ON_ERROR_STOP on
BEGIN;
SELECT hk_validation.assert(current_user = 'hindamiskomponent_app' AND session_user = current_user, 'actual app login');
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.testisessioonid), 'no context denies sessions');
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.tulemustepank), 'no context denies results');
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.yg_tellimused), 'no context denies orders');
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.ylesandepank), 'no context denies shared items');
SELECT set_config('hk.actor','or',true), set_config('hk.operation','test_create',true), set_config('hk.test_id','test-new',true);
INSERT INTO public.testisessioonid (test_id,kasutaja_id,rada_id)
VALUES ('test-new','learner','path') RETURNING test_id;
SELECT hk_validation.expect_error($sql$INSERT INTO public.testisessioonid (test_id,kasutaja_id,rada_id)
    VALUES ('test-other','learner','path')$sql$, '42501');
INSERT INTO public.yg_tellimused (test_id,kursus,graafi_objektid,ylesande_taotlused)
VALUES ('test-new','course','["node","node2"]','[{"node":"node","amount":2},{"node":"node2","amount":5}]') RETURNING id;
SELECT hk_validation.expect_error($sql$INSERT INTO public.yg_tellimused
    (test_id,kursus,graafi_objektid,attempt_count) VALUES ('test-new','course','[]',1)$sql$, '42501');
SELECT hk_validation.expect_error($sql$INSERT INTO public.yg_tellimused
    (test_id,kursus,graafi_objektid,taitmise_tulemus) VALUES ('test-new','course','[]','[]')$sql$, '42501');
SELECT hk_validation.expect_error($sql$INSERT INTO public.yg_tellimused
    (test_id,kursus,graafi_objektid,staatus) VALUES ('test-new','course','[]','tootmises')$sql$, '42501');
WITH inserted AS (INSERT INTO public.graafid_kst (graaf_hash,graafi_struktuur,teadmusruum_maatriks)
    VALUES ('fixture-graph','{}','[]') ON CONFLICT (graaf_hash) DO NOTHING RETURNING *)
SELECT hk_validation.assert((SELECT count(*) = 0 FROM inserted), 'immutable cache conflict read path');
INSERT INTO public.graafid_kst (graaf_hash,graafi_struktuur,teadmusruum_maatriks)
VALUES ('new-graph','{}','[]') RETURNING graaf_hash;
INSERT INTO public.kst_model_cache (graph_hash,configuration_hash,model_schema_version,model_payload)
VALUES ('new-graph','kst-config-v1:sha256:' || repeat('a',64),2,
    jsonb_build_object('schema_version',2,'method','kst','configuration_hash','kst-config-v1:sha256:' || repeat('a',64))) RETURNING graph_hash;

SELECT set_config('hk.operation','test_read',true), set_config('hk.test_id','test-a',true);
SELECT hk_validation.assert((SELECT count(*) = 1 FROM public.testisessioonid), 'read without WHERE sees selected test');
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.tulemustepank), 'OR read has no answer access');
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.yg_tellimused), 'OR read has no queue access');
WITH changed AS (UPDATE public.testisessioonid SET staatus = 'katkenud' RETURNING *)
SELECT hk_validation.assert((SELECT count(*) = 0 FROM changed), 'read operation cannot update');
SELECT set_config('hk.operation','test_launch',true);
SELECT hk_validation.assert((SELECT count(*) = 1 FROM public.testisessioonid), 'OR launch reads selected session');
SELECT set_config('hk.actor','player',true), set_config('hk.operation','player_start',true);
WITH changed AS (UPDATE public.testisessioonid SET tp_seisund = tp_seisund RETURNING test_id)
SELECT hk_validation.assert((SELECT count(*) = 1 AND min(test_id) = 'test-a' FROM changed), 'unscoped update touches only selected test');
SELECT hk_validation.assert((SELECT count(*) = 2 FROM public.tulemustepank), 'start sees own completed answer history');
SELECT hk_validation.assert((SELECT count(*) = 4 FROM public.yg_tellimused), 'start sees own orders');
SELECT hk_validation.expect_error($sql$UPDATE public.testisessioonid SET kasutaja_id = 'changed'$sql$, '42501');
SELECT hk_validation.expect_error($sql$UPDATE public.testisessioonid SET test_id = 'changed'$sql$, '42501');
SELECT hk_validation.expect_error($sql$UPDATE public.yg_tellimused SET staatus = 'viga'$sql$, '42501');

SELECT set_config('hk.operation','player_answer',true);
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.increment_ylesande_kasutus(1,now())), 'usage needs saved current answer');
SELECT hk_validation.expect_error($sql$INSERT INTO public.tulemustepank
    (test_id,yp_id,skoor,valitud_vastus,graafi_objekt_snapshot,tyvi_snapshot,voti_snapshot)
    VALUES ('test-b',1,1,'correct','node','prompt','correct')$sql$, '42501');
INSERT INTO public.tulemustepank
    (test_id,yp_id,skoor,valitud_vastus,vastus_id,graafi_objekt_snapshot,tyvi_snapshot,voti_snapshot)
VALUES ('test-a',1,1,'correct','11111111-1111-1111-1111-111111111111','node','question-time prompt','correct') RETURNING vastus_id;
WITH replay AS (INSERT INTO public.tulemustepank
    (test_id,yp_id,skoor,valitud_vastus,vastus_id,graafi_objekt_snapshot,tyvi_snapshot,voti_snapshot)
    VALUES ('test-a',1,1,'correct','11111111-1111-1111-1111-111111111111','node','replacement','correct')
    ON CONFLICT (vastus_id) DO NOTHING RETURNING *)
SELECT hk_validation.assert((SELECT count(*) = 0 FROM replay), 'replay does not replace snapshots');
SELECT hk_validation.assert((SELECT count(*) = 1 FROM public.increment_ylesande_kasutus(1,'2026-10-05T10:00:00Z')), 'own current saved answer increments usage');
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.increment_ylesande_kasutus(2,now())), 'historical or other-test item cannot increment');
SELECT hk_validation.expect_error($sql$SELECT * FROM public.increment_ylesande_kasutus(1,NULL)$sql$, '22004');
SELECT * FROM public.increment_ylesande_kasutus(1,'2026-10-04T10:00:00Z');
SELECT hk_validation.assert((SELECT viimane_kasutus = '2026-10-05T10:00:00Z'::timestamptz FROM public.ylesandepank WHERE yp_id = 1), 'latest use is monotonic');
SELECT hk_validation.expect_error($sql$UPDATE public.ylesandepank SET ebaadekvaatne_arv = 99 WHERE yp_id = 1$sql$, '42501');
SELECT hk_validation.expect_error($sql$UPDATE public.tulemustepank SET tyvi_snapshot = 'edited'$sql$, '42501');
SELECT hk_validation.expect_error($sql$DELETE FROM public.tulemustepank$sql$, '42501');
SELECT hk_validation.expect_error($sql$TRUNCATE public.testisessioonid$sql$, '42501');
SELECT hk_validation.expect_error($sql$CREATE TABLE public.forbidden (id integer)$sql$, '42501');
SELECT hk_validation.expect_error($sql$CREATE TEMP TABLE forbidden (id integer)$sql$, '42501');
SELECT hk_validation.expect_error($sql$SET ROLE hindamiskomponent_owner$sql$, '42501');
SELECT hk_validation.expect_error($sql$SELECT * FROM public.repo_materjalid$sql$, '42501');
SELECT hk_validation.expect_error($sql$SELECT public.reject_result_mutation()$sql$, '42501');

SELECT set_config('hk.operation','player_report',true);
SELECT hk_validation.assert((SELECT count(*) = 1 FROM public.increment_ebaadekvaatne_arv(1)), 'report current question');
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.increment_ebaadekvaatne_arv(2)), 'report denies historical item');
SELECT hk_validation.expect_error($sql$UPDATE public.ylesandepank SET kasutamiste_arv = 99 WHERE yp_id = 1$sql$, '42501');
SELECT set_config('hk.actor','or',true);
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.testisessioonid), 'wrong actor denies');
SELECT set_config('hk.actor','player',true), set_config('hk.operation','unknown',true);
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.testisessioonid), 'unknown operation denies');
SELECT set_config('hk.operation','player_answer',true), set_config('hk.test_id','',true);
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.testisessioonid), 'empty test ID denies');
SELECT set_config('hk.actor','admin',true), set_config('hk.operation','admin_items',true), set_config('hk.test_id','test-a',true);
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.ylesandepank), 'actor cannot gain another role privileges');
SELECT set_config('hk.actor','player',true), set_config('hk.operation','player_answer',true);
UPDATE public.testisessioonid SET staatus = 'lõpetatud', tp_seisund = '{"current_question":null}', lopp_profiil = '{}' RETURNING test_id;
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.increment_ylesande_kasutus(1,now())), 'completed state cannot increment');
SELECT hk_validation.assert((SELECT tyvi_snapshot = 'question-time prompt' AND juhis_snapshot IS NULL
    AND stiimul_snapshot IS NULL AND arvutuskaik_snapshot IS NULL FROM public.tulemustepank
    WHERE vastus_id = '11111111-1111-1111-1111-111111111111'), 'required snapshots saved; optional absence and replay preserved');
ROLLBACK;
BEGIN;
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.testisessioonid), 'rollback clears local context');
SELECT set_config('hk.actor','or',true), set_config('hk.operation','test_read',true), set_config('hk.test_id','test-b',true);
SELECT hk_validation.assert((SELECT count(*) = 1 FROM public.testisessioonid WHERE test_id = 'test-b'), 'OR can select another authorized test');
COMMIT;
BEGIN;
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.testisessioonid), 'commit clears local context');
ROLLBACK;
