\set ON_ERROR_STOP on
BEGIN;
SELECT hk_validation.assert(current_user = 'hindamiskomponent_worker' AND session_user = current_user, 'actual worker login');
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.yg_tellimused), 'missing context denies queue');
SELECT set_config('hk.actor','worker',true), set_config('hk.operation','worker_generate',true), set_config('hk.test_id','',true);
SELECT hk_validation.assert((SELECT count(*) = 8 FROM public.yg_tellimused), 'worker sees shared queue without test');
SELECT hk_validation.assert((SELECT count(*) = 1 FROM public.repo_materjalid), 'worker reads sources');
SELECT hk_validation.assert((SELECT count(*) = 1 FROM public.yg_reeglid), 'worker reads rules');
SELECT hk_validation.assert((SELECT count(*) = 3 FROM public.ylesandepank), 'worker reads inventory');
SELECT hk_validation.assert((SELECT array_agg(id ORDER BY id) = ARRAY[1,3,7,8]::bigint[]
    FROM public.yg_tellimused WHERE
        (staatus = 'ootel' AND (next_attempt_at IS NULL OR next_attempt_at <= clock_timestamp()))
        OR (staatus = 'tootmises' AND locked_until <= clock_timestamp())), 'NULL/due pending and expired leases eligible; future/terminal excluded');
WITH eligible AS (
    SELECT id FROM public.yg_tellimused WHERE
        (staatus = 'ootel' AND (next_attempt_at IS NULL OR next_attempt_at <= clock_timestamp()))
        OR (staatus = 'tootmises' AND locked_until <= clock_timestamp())
    ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1
), claimed AS (
    UPDATE public.yg_tellimused AS job SET staatus = 'tootmises', attempt_count = attempt_count + 1,
        claim_token = 'aaaaaaaa-1111-1111-1111-111111111111', locked_until = clock_timestamp() + interval '5 minutes'
    FROM eligible WHERE job.id = eligible.id RETURNING job.*
)
SELECT hk_validation.assert((SELECT count(*) = 1 AND min(id) = 1 AND min(attempt_count) = 1 FROM claimed), 'worker claims via row lock and RETURNING');
-- Retry then due claim, keeping the nonterminal order alive.
UPDATE public.yg_tellimused SET staatus = 'ootel', last_error = 'sanitized failure',
    next_attempt_at = clock_timestamp() - interval '1 second', locked_until = NULL, claim_token = NULL WHERE id = 1;
UPDATE public.yg_tellimused SET staatus = 'tootmises', attempt_count = attempt_count + 1,
    locked_until = clock_timestamp() + interval '5 minutes', claim_token = 'bbbbbbbb-1111-1111-1111-111111111111'
WHERE id = 1 AND staatus = 'ootel' AND next_attempt_at <= clock_timestamp() RETURNING id;
-- Reclaim the expired synthetic lease. A stale token cannot complete it when
-- the worker performs the required ownership check in its locked transaction.
SELECT id FROM public.yg_tellimused WHERE id = 3 FOR UPDATE;
UPDATE public.yg_tellimused SET attempt_count = attempt_count + 1,
    claim_token = 'cccccccc-1111-1111-1111-111111111111', locked_until = clock_timestamp() + interval '5 minutes' WHERE id = 3;
WITH stale AS (UPDATE public.yg_tellimused SET staatus = 'tehtud'
    WHERE id = 3 AND staatus = 'tootmises' AND claim_token = '33333333-3333-3333-3333-333333333333'
    AND locked_until > clock_timestamp() RETURNING *)
SELECT hk_validation.assert((SELECT count(*) = 0 FROM stale), 'stale ownership check rejects completion');
UPDATE public.yg_tellimused SET locked_until = clock_timestamp() - interval '1 second' WHERE id = 3;
WITH expired AS (UPDATE public.yg_tellimused SET staatus = 'tehtud'
    WHERE id = 3 AND staatus = 'tootmises' AND claim_token = 'cccccccc-1111-1111-1111-111111111111'
    AND locked_until > clock_timestamp() RETURNING *)
SELECT hk_validation.assert((SELECT count(*) = 0 FROM expired), 'expired ownership check rejects completion');
-- Failed completion subtransaction leaves neither inserted item nor terminal status.
SELECT hk_validation.expect_error($sql$DO $body$
BEGIN
    INSERT INTO public.ylesandepank (kursus,graafi_objekt,graafi_ema_objekt,tyvi,voti,distraktor_1,distraktor_2,distraktor_3)
    VALUES ('course','rollback-node','parent','prompt','key','one','two','three');
    UPDATE public.yg_tellimused SET staatus = 'tehtud' WHERE id = 1;
    RAISE EXCEPTION 'synthetic completion failure';
END;
$body$ $sql$, 'P0001');
SELECT hk_validation.assert((SELECT count(*) = 0 FROM public.ylesandepank WHERE graafi_objekt = 'rollback-node'), 'completion rollback removes generated items');
SELECT hk_validation.assert((SELECT staatus = 'tootmises' FROM public.yg_tellimused WHERE id = 1), 'completion rollback preserves nonterminal status');
SELECT id FROM public.yg_tellimused WHERE id = 1 AND staatus = 'tootmises'
    AND claim_token = 'bbbbbbbb-1111-1111-1111-111111111111' AND locked_until > clock_timestamp() FOR UPDATE;
INSERT INTO public.ylesandepank (kursus,graafi_objekt,graafi_ema_objekt,tyvi,voti,distraktor_1,distraktor_2,distraktor_3,staatus)
VALUES ('course','generated-node','parent','prompt','key','one','two','three','kasutatav') RETURNING yp_id;
UPDATE public.yg_tellimused SET staatus = 'tehtud', completed_at = clock_timestamp(),
    locked_until = NULL, claim_token = NULL, next_attempt_at = NULL, last_error = NULL,
    taitmise_tulemus = '[{"node":"node","requested":1,"baseline_usable":0,"created":1,"usable_after":1,"remaining":0}]'
WHERE id = 1 RETURNING id;
SELECT hk_validation.expect_error($sql$UPDATE public.yg_tellimused SET test_id = 'other' WHERE id = 1$sql$, '42501');
SELECT hk_validation.expect_error($sql$UPDATE public.yg_tellimused SET ylesande_taotlused = '[]' WHERE id = 1$sql$, '42501');
SELECT hk_validation.expect_error($sql$UPDATE public.ylesandepank SET tyvi = 'other' WHERE yp_id = 1$sql$, '42501');
SELECT hk_validation.expect_error($sql$INSERT INTO public.yg_tellimused (test_id,kursus,graafi_objektid)
    VALUES ('other','course','[]')$sql$, '42501');
SELECT hk_validation.expect_error($sql$SELECT * FROM public.testisessioonid$sql$, '42501');
SELECT hk_validation.expect_error($sql$SELECT * FROM public.tulemustepank$sql$, '42501');
SELECT hk_validation.expect_error($sql$SELECT * FROM public.increment_ylesande_kasutus(1,now())$sql$, '42501');
SELECT hk_validation.expect_error($sql$DELETE FROM public.yg_tellimused$sql$, '42501');
SELECT hk_validation.expect_error($sql$TRUNCATE public.yg_tellimused$sql$, '42501');
SELECT hk_validation.expect_error($sql$CREATE TABLE public.forbidden (id integer)$sql$, '42501');
SELECT hk_validation.expect_error($sql$SET ROLE hindamiskomponent_admin$sql$, '42501');
ROLLBACK;
