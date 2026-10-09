\set ON_ERROR_STOP on
BEGIN;
SELECT hk_validation.assert(current_user = 'hindamiskomponent_admin' AND session_user = current_user, 'actual admin login');
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.testisessioonid), 'no context denies admin sessions');
SELECT set_config('hk.actor','admin',true), set_config('hk.operation','admin_sources',true), set_config('hk.test_id','',true);
INSERT INTO public.repo_materjalid (kursus,pealkiri,sisu_tekst) VALUES ('course','new source','body') RETURNING id;
SELECT hk_validation.assert((SELECT count(*) = 2 FROM public.repo_materjalid), 'admin source creation/read');
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.testisessioonid), 'maintenance has no session access');
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.tulemustepank), 'maintenance has no result access');
SELECT set_config('hk.operation','admin_rules',true);
INSERT INTO public.yg_reeglid (kursus,reegli_kirjeldus,naidis_json) VALUES ('course','new rule','{}') RETURNING id;
SELECT hk_validation.assert((SELECT count(*) = 2 FROM public.yg_reeglid), 'admin rule creation/read');
SELECT set_config('hk.operation','admin_items',true);
UPDATE public.ylesandepank SET tyvi = 'edited prompt', voti = 'edited key' WHERE yp_id = 2 RETURNING yp_id;
INSERT INTO public.ylesandepank (kursus,graafi_objekt,graafi_ema_objekt,tyvi,voti,distraktor_1,distraktor_2,distraktor_3)
VALUES ('course','node','parent','new prompt','key','one','two','three') RETURNING yp_id;
SELECT hk_validation.expect_error($sql$UPDATE public.ylesandepank SET kasutamiste_arv = 99 WHERE yp_id = 1$sql$, '42501');
SELECT hk_validation.expect_error($sql$UPDATE public.ylesandepank SET kursus = 'other' WHERE yp_id = 1$sql$, '42501');
SELECT hk_validation.expect_error($sql$UPDATE public.ylesandepank SET yp_id = 100 WHERE yp_id = 1$sql$, '42501');
SELECT set_config('hk.operation','admin_configuration',true);
WITH version AS (INSERT INTO public.kst_configuration_versions
    (schema_version,configuration,configuration_hash,created_by)
    VALUES (1,'{"schema_version":1}','kst-config-v1:sha256:' || repeat('b',64),'admin') RETURNING id)
INSERT INTO public.kst_configuration_activations (configuration_version_id,activated_by)
SELECT id,'admin' FROM version RETURNING id;
SELECT hk_validation.assert((SELECT count(*) = 2 FROM public.kst_configuration_versions), 'admin configuration creation');
SELECT hk_validation.expect_error($sql$UPDATE public.kst_configuration_versions SET created_by = 'other'$sql$, '42501');
SELECT set_config('hk.operation','test_read',true), set_config('hk.test_id','test-a',true);
SELECT hk_validation.assert((SELECT count(*) = 1 FROM public.testisessioonid), 'simulation read selected test');
SELECT set_config('hk.operation','test_launch',true);
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.testisessioonid), 'simulation cannot launch player token');
SELECT set_config('hk.operation','player_report',true);
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.testisessioonid), 'simulation cannot report questions');
SELECT hk_validation.expect_error($sql$SELECT * FROM public.increment_ebaadekvaatne_arv(1)$sql$, '42501');
SELECT hk_validation.expect_error($sql$UPDATE public.ylesandepank SET ebaadekvaatne_arv = 1 WHERE yp_id = 1$sql$, '42501');
SELECT set_config('hk.operation','player_answer',true);
SELECT hk_validation.assert((SELECT bool_and(tyvi_snapshot = 'saved prompt' AND voti_snapshot = 'correct')
    FROM public.tulemustepank), 'historical snapshots survive item edits');
INSERT INTO public.tulemustepank (test_id,yp_id,skoor,valitud_vastus,vastus_id,
    graafi_objekt_snapshot,tyvi_snapshot,voti_snapshot)
VALUES ('test-a',1,1,'correct','11111111-1111-1111-1111-111111111111','node','saved','correct') RETURNING id;
SELECT hk_validation.assert((SELECT count(*) = 1 FROM public.increment_ylesande_kasutus(1,now())), 'simulation usage allowed');
SELECT hk_validation.expect_error($sql$UPDATE public.ylesandepank SET tyvi = 'simulation edit' WHERE yp_id = 1$sql$, '42501');
WITH changed AS (UPDATE public.testisessioonid SET tp_seisund = tp_seisund RETURNING *)
SELECT hk_validation.assert((SELECT count(*) = 1 FROM changed), 'simulation updates only selected test');
SELECT hk_validation.expect_error($sql$DELETE FROM public.repo_materjalid$sql$, '42501');
SELECT hk_validation.expect_error($sql$TRUNCATE public.ylesandepank$sql$, '42501');
SELECT hk_validation.expect_error($sql$CREATE TABLE public.forbidden (id integer)$sql$, '42501');
SELECT hk_validation.expect_error($sql$SET ROLE hindamiskomponent_app$sql$, '42501');
ROLLBACK;
