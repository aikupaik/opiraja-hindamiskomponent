-- Fresh PostgreSQL 16 application schema, derived from production_schema_v1_draft.md
-- and review_queries_{1,2,3,4}.csv. No source rows, webhook or credentials.
-- Run with psql as hindamiskomponent_migrator in hindamiskomponent.
-- Roles/database are provisioned separately. See README.md for prerequisites.
-- Intentionally not rerunnable: a second installation must fail and roll back.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL ROLE hindamiskomponent_owner;
SET LOCAL search_path = '';

DO $preflight$
DECLARE
    runtime_name text;
    other_name text;
    role_record record;
BEGIN
    IF current_database() <> 'hindamiskomponent'
       OR current_setting('server_version_num')::integer NOT BETWEEN 160000 AND 169999 THEN
        RAISE EXCEPTION 'V1 requires PostgreSQL 16 database hindamiskomponent';
    END IF;
    IF (SELECT datdba FROM pg_catalog.pg_database WHERE datname = current_database())
       <> 'hindamiskomponent_owner'::regrole::oid THEN
        RAISE EXCEPTION 'Database must be owned by hindamiskomponent_owner';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_extension WHERE extname = 'pg_stat_statements') THEN
        RAISE EXCEPTION 'DBA must first run production_observability.sql';
    END IF;
    SELECT * INTO STRICT role_record FROM pg_catalog.pg_roles
        WHERE rolname = 'hindamiskomponent_owner';
    IF role_record.rolcanlogin OR role_record.rolsuper OR role_record.rolbypassrls
       OR role_record.rolcreatedb OR role_record.rolcreaterole THEN
        RAISE EXCEPTION 'Owner must be NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE';
    END IF;
    SELECT * INTO STRICT role_record FROM pg_catalog.pg_roles
        WHERE rolname = 'hindamiskomponent_migrator';
    IF NOT role_record.rolcanlogin OR role_record.rolinherit OR role_record.rolsuper
       OR role_record.rolbypassrls OR role_record.rolcreatedb OR role_record.rolcreaterole THEN
        RAISE EXCEPTION 'Migrator must be LOGIN NOINHERIT without elevated attributes';
    END IF;
    FOREACH runtime_name IN ARRAY ARRAY[
        'hindamiskomponent_app', 'hindamiskomponent_admin', 'hindamiskomponent_worker'
    ] LOOP
        SELECT * INTO STRICT role_record FROM pg_catalog.pg_roles WHERE rolname = runtime_name;
        IF NOT role_record.rolcanlogin OR role_record.rolsuper OR role_record.rolbypassrls
           OR role_record.rolcreatedb OR role_record.rolcreaterole THEN
            RAISE EXCEPTION 'Unsafe attributes on runtime role %', runtime_name;
        END IF;
        -- MEMBER follows indirect membership, including NOINHERIT paths.
        FOREACH other_name IN ARRAY ARRAY[
            'hindamiskomponent_owner', 'hindamiskomponent_migrator',
            'hindamiskomponent_app', 'hindamiskomponent_admin', 'hindamiskomponent_worker'
        ] LOOP
            IF other_name <> runtime_name AND pg_catalog.pg_has_role(runtime_name, other_name, 'MEMBER') THEN
                RAISE EXCEPTION 'Runtime % has membership in %', runtime_name, other_name;
            END IF;
        END LOOP;
        IF EXISTS (SELECT FROM pg_catalog.pg_class WHERE relowner = role_record.oid
                   AND relnamespace = 'public'::regnamespace)
           OR EXISTS (SELECT FROM pg_catalog.pg_proc WHERE proowner = role_record.oid
                      AND pronamespace = 'public'::regnamespace) THEN
            RAISE EXCEPTION 'Runtime % already owns public objects', runtime_name;
        END IF;
    END LOOP;
END;
$preflight$;

REVOKE ALL ON DATABASE hindamiskomponent FROM PUBLIC,
    hindamiskomponent_app, hindamiskomponent_admin, hindamiskomponent_worker;
GRANT CONNECT ON DATABASE hindamiskomponent TO hindamiskomponent_migrator,
    hindamiskomponent_app, hindamiskomponent_admin, hindamiskomponent_worker;
REVOKE ALL ON SCHEMA public FROM PUBLIC,
    hindamiskomponent_app, hindamiskomponent_admin, hindamiskomponent_worker;
GRANT USAGE ON SCHEMA public TO hindamiskomponent_migrator,
    hindamiskomponent_app, hindamiskomponent_admin, hindamiskomponent_worker;

-- Clear both global and per-schema defaults: per-schema revocations alone
-- cannot remove a grant inherited from global default privileges.
ALTER DEFAULT PRIVILEGES FOR ROLE hindamiskomponent_owner
    REVOKE ALL ON TABLES FROM PUBLIC, hindamiskomponent_app, hindamiskomponent_admin, hindamiskomponent_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE hindamiskomponent_owner IN SCHEMA public
    REVOKE ALL ON TABLES FROM PUBLIC, hindamiskomponent_app, hindamiskomponent_admin, hindamiskomponent_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE hindamiskomponent_owner
    REVOKE ALL ON SEQUENCES FROM PUBLIC, hindamiskomponent_app, hindamiskomponent_admin, hindamiskomponent_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE hindamiskomponent_owner IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM PUBLIC, hindamiskomponent_app, hindamiskomponent_admin, hindamiskomponent_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE hindamiskomponent_owner
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, hindamiskomponent_app, hindamiskomponent_admin, hindamiskomponent_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE hindamiskomponent_owner IN SCHEMA public
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, hindamiskomponent_app, hindamiskomponent_admin, hindamiskomponent_worker;

CREATE TABLE public.graafid_kst (
    graaf_hash text NOT NULL,
    graafi_struktuur jsonb NOT NULL,
    teadmusruum_maatriks jsonb NOT NULL,
    loodud timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT graafid_kst_pkey PRIMARY KEY (graaf_hash)
);

CREATE TABLE public.kst_configuration_versions (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    schema_version integer NOT NULL,
    configuration jsonb NOT NULL,
    configuration_hash text NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT kst_configuration_versions_pkey PRIMARY KEY (id),
    CONSTRAINT kst_configuration_versions_configuration_hash_key UNIQUE (configuration_hash),
    CONSTRAINT kst_configuration_versions_configuration_object CHECK (jsonb_typeof(configuration) = 'object'),
    CONSTRAINT kst_configuration_versions_created_by_nonblank CHECK (length(btrim(created_by)) > 0),
    CONSTRAINT kst_configuration_versions_hash_format CHECK (configuration_hash ~ '^kst-config-v1:sha256:[0-9a-f]{64}$'),
    CONSTRAINT kst_configuration_versions_schema_version_v1 CHECK (schema_version = 1),
    CONSTRAINT kst_configuration_versions_payload_schema_version CHECK (
        (jsonb_typeof(configuration -> 'schema_version') = 'number'
         AND configuration ->> 'schema_version' = '1') IS TRUE
    )
);

CREATE TABLE public.kst_configuration_activations (
    id bigint GENERATED ALWAYS AS IDENTITY (START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1 NO CYCLE),
    configuration_version_id uuid NOT NULL,
    activated_by text NOT NULL,
    activated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT kst_configuration_activations_pkey PRIMARY KEY (id),
    CONSTRAINT kst_configuration_activations_activated_by_nonblank CHECK (length(btrim(activated_by)) > 0),
    CONSTRAINT kst_configuration_activations_configuration_version_id_fkey
        FOREIGN KEY (configuration_version_id) REFERENCES public.kst_configuration_versions (id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
);

CREATE TABLE public.kst_model_cache (
    graph_hash text NOT NULL,
    configuration_hash text NOT NULL,
    model_schema_version integer NOT NULL,
    model_payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT kst_model_cache_pkey PRIMARY KEY (graph_hash, configuration_hash, model_schema_version),
    CONSTRAINT kst_model_cache_configuration_hash_fkey FOREIGN KEY (configuration_hash)
        REFERENCES public.kst_configuration_versions (configuration_hash) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT kst_model_cache_graph_hash_fkey FOREIGN KEY (graph_hash)
        REFERENCES public.graafid_kst (graaf_hash) ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT kst_model_cache_supported_schema CHECK (model_schema_version = 2),
    CONSTRAINT kst_model_cache_payload_shape CHECK ((
        jsonb_typeof(model_payload) = 'object'
        AND model_payload ?& ARRAY['schema_version', 'method', 'configuration_hash']
        AND model_payload ->> 'schema_version' = model_schema_version::text
        AND model_payload ->> 'method' = 'kst'
        AND model_payload ->> 'configuration_hash' = configuration_hash
    ) IS TRUE)
);

CREATE TABLE public.repo_materjalid (
    id bigint GENERATED BY DEFAULT AS IDENTITY (START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1 NO CYCLE),
    kursus text NOT NULL,
    pealkiri text,
    allika_url text,
    sisu_tekst text,
    lisatud timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT repo_materjalid_pkey PRIMARY KEY (id)
);

CREATE TABLE public.testisessioonid (
    test_id text NOT NULL,
    kasutaja_id text NOT NULL,
    rada_id text NOT NULL,
    graaf_hash text,
    staatus text NOT NULL DEFAULT 'planeerimisel',
    alustatud timestamptz NOT NULL DEFAULT now(),
    lopp_profiil jsonb,
    testi_loogika jsonb NOT NULL DEFAULT '{}',
    metoodika text NOT NULL DEFAULT 'kst',
    tp_seisund jsonb NOT NULL DEFAULT '{}',
    kursus text,
    eesmark text,
    CONSTRAINT testisessioonid_pkey PRIMARY KEY (test_id),
    CONSTRAINT chk_sessiooni_staatus CHECK (staatus IN ('planeerimisel', 'aktiivne', 'lõpetatud', 'katkenud')),
    CONSTRAINT testisessioonid_metoodika_check CHECK (metoodika IN ('ct', 'kst', 'irt', 'dina')),
    -- Preserve source ON UPDATE NO ACTION; only deletion behavior changes.
    CONSTRAINT testisessioonid_graaf_hash_fkey FOREIGN KEY (graaf_hash)
        REFERENCES public.graafid_kst (graaf_hash) ON DELETE RESTRICT
);

CREATE TABLE public.yg_reeglid (
    id bigint GENERATED BY DEFAULT AS IDENTITY (START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1 NO CYCLE),
    kursus text NOT NULL,
    reegli_kirjeldus text NOT NULL,
    naidis_json jsonb NOT NULL,
    CONSTRAINT yg_reeglid_pkey PRIMARY KEY (id)
);

CREATE TABLE public.yg_tellimused (
    id bigint GENERATED BY DEFAULT AS IDENTITY (START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1 NO CYCLE),
    test_id text NOT NULL, -- Informational correlation: intentionally no FK.
    kursus text NOT NULL,
    graafi_objektid jsonb NOT NULL,
    kognitiivne_tase text NOT NULL DEFAULT 'mõistab',
    maht integer NOT NULL DEFAULT 1,
    staatus text NOT NULL DEFAULT 'ootel',
    loodud timestamptz NOT NULL DEFAULT now(),
    ylesande_taotlused jsonb DEFAULT '[]',
    taitmise_tulemus jsonb DEFAULT '[]',
    graafi_ema_objekt text,
    attempt_count integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz,
    locked_until timestamptz,
    claim_token uuid,
    last_error text,
    completed_at timestamptz,
    CONSTRAINT yg_tellimused_pkey PRIMARY KEY (id),
    CONSTRAINT chk_tellimuse_kognitiivne_tase CHECK (kognitiivne_tase IN ('mäletab', 'mõistab', 'rakendab', 'analüüsib', 'hindab', 'loob')),
    CONSTRAINT chk_tellimuse_staatus CHECK (staatus IN ('ootel', 'tootmises', 'tehtud', 'viga')),
    CONSTRAINT yg_tellimused_maht_positive CHECK (maht > 0),
    CONSTRAINT yg_tellimused_attempt_count_nonnegative CHECK (attempt_count >= 0)
);

CREATE TABLE public.ylesandepank (
    yp_id bigint GENERATED BY DEFAULT AS IDENTITY (START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1 NO CYCLE),
    kursus text NOT NULL,
    graafi_objekt text NOT NULL,
    graafi_ema_objekt text NOT NULL,
    kognitiivne_tase text NOT NULL DEFAULT 'mõistab',
    juhis text,
    tyvi text NOT NULL,
    stiimul text,
    voti text NOT NULL,
    distraktor_1 text NOT NULL,
    distraktor_2 text NOT NULL,
    distraktor_3 text NOT NULL,
    skoor integer NOT NULL DEFAULT 1,
    irt_a numeric(4,2) NOT NULL DEFAULT 1.00,
    irt_b numeric(4,2) NOT NULL DEFAULT 0.00,
    beeta_error numeric(3,2) NOT NULL DEFAULT 0.05,
    g_guess numeric(3,2) NOT NULL DEFAULT 0.25,
    staatus text NOT NULL DEFAULT 'kavand',
    kasutamiste_arv integer NOT NULL DEFAULT 0,
    viimane_kasutus timestamptz,
    arvutuskaik text,
    ebaadekvaatne_arv integer NOT NULL DEFAULT 0,
    CONSTRAINT ylesandepank_pkey PRIMARY KEY (yp_id),
    CONSTRAINT chk_ylesande_staatus CHECK (staatus IN ('kavand', 'kasutatav', 'läbi vaatamisel', 'arhiivis')),
    CONSTRAINT chk_yp_kognitiivne_tase CHECK (kognitiivne_tase IN ('mäletab', 'mõistab', 'rakendab', 'analüüsib', 'hindab', 'loob')),
    CONSTRAINT ylesandepank_ebaadekvaatne_arv_nonnegative CHECK (ebaadekvaatne_arv >= 0)
);

CREATE TABLE public.tulemustepank (
    id bigint GENERATED BY DEFAULT AS IDENTITY (START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 CACHE 1 NO CYCLE),
    test_id text NOT NULL,
    yp_id bigint NOT NULL,
    skoor integer NOT NULL,
    valitud_vastus text NOT NULL,
    vastatud_ajal timestamptz NOT NULL DEFAULT now(),
    vastus_id uuid NOT NULL DEFAULT gen_random_uuid(),
    graafi_objekt_snapshot text NOT NULL,
    juhis_snapshot text,
    tyvi_snapshot text NOT NULL,
    stiimul_snapshot text,
    voti_snapshot text NOT NULL,
    arvutuskaik_snapshot text,
    CONSTRAINT tulemustepank_pkey PRIMARY KEY (id),
    CONSTRAINT tulemustepank_test_id_fkey FOREIGN KEY (test_id)
        REFERENCES public.testisessioonid (test_id) ON DELETE RESTRICT,
    CONSTRAINT tulemustepank_yp_id_fkey FOREIGN KEY (yp_id)
        REFERENCES public.ylesandepank (yp_id) ON DELETE RESTRICT,
    CONSTRAINT tulemustepank_vastus_id_key UNIQUE (vastus_id)
    -- Repeated answers to the same (test_id, yp_id) remain possible.
);

CREATE INDEX kst_configuration_activations_version_history_idx
    ON public.kst_configuration_activations (configuration_version_id, id DESC);
CREATE INDEX ylesandepank_usable_node_order_idx
    ON public.ylesandepank (graafi_objekt, yp_id) WHERE staatus = 'kasutatav';
CREATE INDEX tulemustepank_test_id_idx ON public.tulemustepank (test_id);

CREATE FUNCTION public.increment_ebaadekvaatne_arv(p_yp_id bigint)
RETURNS TABLE(yp_id bigint) LANGUAGE sql SECURITY INVOKER SET search_path = ''
AS $function$
    UPDATE public.ylesandepank
    SET ebaadekvaatne_arv = coalesce(ebaadekvaatne_arv, 0) + 1
    WHERE ylesandepank.yp_id = p_yp_id
    RETURNING ylesandepank.yp_id;
$function$;

CREATE FUNCTION public.increment_ylesande_kasutus(p_yp_id bigint, p_used_at timestamptz)
RETURNS TABLE(yp_id bigint) LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $function$
BEGIN
    IF p_used_at IS NULL THEN
        RAISE EXCEPTION 'p_used_at must not be null' USING ERRCODE = '22004';
    END IF;
    RETURN QUERY UPDATE public.ylesandepank AS item
    SET kasutamiste_arv = item.kasutamiste_arv + 1,
        viimane_kasutus = CASE WHEN item.viimane_kasutus IS NULL OR item.viimane_kasutus < p_used_at
                             THEN p_used_at ELSE item.viimane_kasutus END
    WHERE item.yp_id = p_yp_id RETURNING item.yp_id;
END;
$function$;

CREATE FUNCTION public.reject_kst_configuration_mutation()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $function$
BEGIN
    RAISE EXCEPTION '% is append-only; update and delete are forbidden', TG_TABLE_NAME;
END;
$function$;
CREATE FUNCTION public.reject_kst_model_cache_mutation()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $function$
BEGIN
    RAISE EXCEPTION 'kst_model_cache is immutable; update and delete are forbidden';
END;
$function$;
CREATE FUNCTION public.reject_graph_mutation()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $function$
BEGIN
    RAISE EXCEPTION 'graafid_kst is append-only; update and delete are forbidden';
END;
$function$;
CREATE FUNCTION public.reject_result_mutation()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $function$
BEGIN
    RAISE EXCEPTION 'tulemustepank is append-only; update and delete are forbidden';
END;
$function$;

CREATE TRIGGER kst_configuration_versions_append_only BEFORE UPDATE OR DELETE
    ON public.kst_configuration_versions FOR EACH ROW EXECUTE FUNCTION public.reject_kst_configuration_mutation();
CREATE TRIGGER kst_configuration_activations_append_only BEFORE UPDATE OR DELETE
    ON public.kst_configuration_activations FOR EACH ROW EXECUTE FUNCTION public.reject_kst_configuration_mutation();
CREATE TRIGGER kst_model_cache_append_only BEFORE UPDATE OR DELETE
    ON public.kst_model_cache FOR EACH ROW EXECUTE FUNCTION public.reject_kst_model_cache_mutation();
CREATE TRIGGER graafid_kst_append_only BEFORE UPDATE OR DELETE
    ON public.graafid_kst FOR EACH ROW EXECUTE FUNCTION public.reject_graph_mutation();
CREATE TRIGGER tulemustepank_append_only BEFORE UPDATE OR DELETE
    ON public.tulemustepank FOR EACH ROW EXECUTE FUNCTION public.reject_result_mutation();

-- Private, SECURITY INVOKER predicates centralize the trusted context vocabulary.
-- They never elevate privileges or read application rows.
CREATE SCHEMA hk_private AUTHORIZATION hindamiskomponent_owner;
REVOKE ALL ON SCHEMA hk_private FROM PUBLIC;
GRANT USAGE ON SCHEMA hk_private TO hindamiskomponent_app, hindamiskomponent_admin, hindamiskomponent_worker;

CREATE FUNCTION hk_private.assessment_context(operations text[])
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path = ''
AS $function$
    SELECT coalesce(
        nullif(current_setting('hk.test_id', true), '') IS NOT NULL
        AND current_setting('hk.operation', true) = ANY(operations)
        AND (
            (current_user = 'hindamiskomponent_app' AND (
                (current_setting('hk.actor', true) = 'or'
                 AND current_setting('hk.operation', true) IN ('test_create', 'test_read', 'test_launch'))
                OR (current_setting('hk.actor', true) = 'player'
                    AND current_setting('hk.operation', true) IN ('player_start', 'player_answer', 'player_report'))
            ))
            OR (current_user = 'hindamiskomponent_admin'
                AND current_setting('hk.actor', true) = 'admin'
                AND current_setting('hk.operation', true) IN ('test_create', 'test_read', 'player_start', 'player_answer'))
        ), false);
$function$;
CREATE FUNCTION hk_private.selected_test(candidate text)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path = ''
AS $function$
    SELECT coalesce(candidate = nullif(current_setting('hk.test_id', true), ''), false);
$function$;
CREATE FUNCTION hk_private.admin_context(operation text)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path = ''
AS $function$
    SELECT coalesce(current_user = 'hindamiskomponent_admin'
        AND current_setting('hk.actor', true) = 'admin'
        AND current_setting('hk.operation', true) = operation
        AND operation IN ('admin_sources', 'admin_rules', 'admin_items', 'admin_configuration'), false);
$function$;
CREATE FUNCTION hk_private.worker_context()
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path = ''
AS $function$
    SELECT coalesce(current_user = 'hindamiskomponent_worker'
        AND current_setting('hk.actor', true) = 'worker'
        AND current_setting('hk.operation', true) = 'worker_generate', false);
$function$;

-- A role's column grants are the union of its operations. RLS restricts rows,
-- but cannot by itself stop a simulated answer from editing item content, or a
-- report from changing usage. This guard restricts changed columns per operation.
CREATE FUNCTION hk_private.guard_item_update()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $function$
DECLARE
    allowed_columns text[];
    item_maintenance boolean := false;
BEGIN
    IF current_user = 'hindamiskomponent_owner' THEN
        RETURN NEW;
    END IF;
    IF current_user = 'hindamiskomponent_admin' THEN
        item_maintenance := hk_private.admin_context('admin_items');
    END IF;
    IF item_maintenance THEN
        allowed_columns := ARRAY['juhis', 'tyvi', 'stiimul', 'voti', 'distraktor_1', 'distraktor_2',
                                 'distraktor_3', 'staatus', 'irt_a', 'irt_b', 'beeta_error', 'g_guess'];
    ELSIF hk_private.assessment_context(ARRAY['player_answer']) THEN
        allowed_columns := ARRAY['kasutamiste_arv', 'viimane_kasutus'];
    ELSIF hk_private.assessment_context(ARRAY['player_report']) THEN
        allowed_columns := ARRAY['ebaadekvaatne_arv'];
    ELSE
        RAISE EXCEPTION 'Item update operation is not authorized' USING ERRCODE = '42501';
    END IF;
    IF (to_jsonb(OLD) - allowed_columns) IS DISTINCT FROM (to_jsonb(NEW) - allowed_columns) THEN
        RAISE EXCEPTION 'Item columns are not authorized for this operation' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END;
$function$;
CREATE TRIGGER ylesandepank_operation_update BEFORE UPDATE ON public.ylesandepank
    FOR EACH ROW EXECUTE FUNCTION hk_private.guard_item_update();

-- Owner policy is deliberately role-targeted; it cannot admit runtime rows.
DO $rls$
DECLARE table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'graafid_kst', 'kst_configuration_versions', 'kst_configuration_activations', 'kst_model_cache',
        'repo_materjalid', 'testisessioonid', 'tulemustepank', 'yg_reeglid', 'yg_tellimused', 'ylesandepank'
    ] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format('CREATE POLICY owner_migration ON public.%I FOR ALL TO hindamiskomponent_owner USING (true) WITH CHECK (true)', table_name);
    END LOOP;
END;
$rls$;

CREATE POLICY assessment_select ON public.testisessioonid FOR SELECT
    TO hindamiskomponent_app, hindamiskomponent_admin USING (
        hk_private.selected_test(test_id)
        AND hk_private.assessment_context(ARRAY['test_create', 'test_read', 'test_launch', 'player_start', 'player_answer', 'player_report'])
    );
CREATE POLICY assessment_insert ON public.testisessioonid FOR INSERT
    TO hindamiskomponent_app, hindamiskomponent_admin WITH CHECK (
        hk_private.selected_test(test_id) AND hk_private.assessment_context(ARRAY['test_create'])
    );
CREATE POLICY assessment_update ON public.testisessioonid FOR UPDATE
    TO hindamiskomponent_app, hindamiskomponent_admin USING (
        hk_private.selected_test(test_id) AND hk_private.assessment_context(ARRAY['player_start', 'player_answer'])
    ) WITH CHECK (
        hk_private.selected_test(test_id) AND hk_private.assessment_context(ARRAY['player_start', 'player_answer'])
    );

CREATE POLICY assessment_select ON public.tulemustepank FOR SELECT
    TO hindamiskomponent_app, hindamiskomponent_admin USING (
        hk_private.selected_test(test_id) AND hk_private.assessment_context(ARRAY['player_start', 'player_answer'])
    );
CREATE POLICY assessment_insert ON public.tulemustepank FOR INSERT
    TO hindamiskomponent_app, hindamiskomponent_admin WITH CHECK (
        hk_private.selected_test(test_id) AND hk_private.assessment_context(ARRAY['player_answer'])
    );

CREATE POLICY assessment_select ON public.yg_tellimused FOR SELECT
    TO hindamiskomponent_app, hindamiskomponent_admin USING (
        hk_private.selected_test(test_id) AND hk_private.assessment_context(ARRAY['test_create', 'player_start'])
    );
CREATE POLICY assessment_insert ON public.yg_tellimused FOR INSERT
    TO hindamiskomponent_app, hindamiskomponent_admin WITH CHECK (
        hk_private.selected_test(test_id) AND hk_private.assessment_context(ARRAY['test_create', 'player_start'])
        AND staatus = 'ootel'
    );
CREATE POLICY worker_select ON public.yg_tellimused FOR SELECT
    TO hindamiskomponent_worker USING (hk_private.worker_context());
CREATE POLICY worker_update ON public.yg_tellimused FOR UPDATE
    TO hindamiskomponent_worker USING (hk_private.worker_context()) WITH CHECK (hk_private.worker_context());

CREATE POLICY assessment_select ON public.graafid_kst FOR SELECT
    TO hindamiskomponent_app, hindamiskomponent_admin
    USING (hk_private.assessment_context(ARRAY['test_create', 'player_start']));
CREATE POLICY assessment_insert ON public.graafid_kst FOR INSERT
    TO hindamiskomponent_app, hindamiskomponent_admin
    WITH CHECK (hk_private.assessment_context(ARRAY['test_create', 'player_start']));
CREATE POLICY assessment_select ON public.kst_model_cache FOR SELECT
    TO hindamiskomponent_app, hindamiskomponent_admin
    USING (hk_private.assessment_context(ARRAY['test_create', 'player_start']));
CREATE POLICY assessment_insert ON public.kst_model_cache FOR INSERT
    TO hindamiskomponent_app, hindamiskomponent_admin
    WITH CHECK (hk_private.assessment_context(ARRAY['test_create', 'player_start']));

CREATE POLICY assessment_select ON public.kst_configuration_versions FOR SELECT
    TO hindamiskomponent_app, hindamiskomponent_admin
    USING (hk_private.assessment_context(ARRAY['test_create', 'player_start']));
CREATE POLICY assessment_select ON public.kst_configuration_activations FOR SELECT
    TO hindamiskomponent_app, hindamiskomponent_admin
    USING (hk_private.assessment_context(ARRAY['test_create', 'player_start']));
CREATE POLICY admin_select ON public.kst_configuration_versions FOR SELECT
    TO hindamiskomponent_admin USING (hk_private.admin_context('admin_configuration'));
CREATE POLICY admin_insert ON public.kst_configuration_versions FOR INSERT
    TO hindamiskomponent_admin WITH CHECK (hk_private.admin_context('admin_configuration'));
CREATE POLICY admin_select ON public.kst_configuration_activations FOR SELECT
    TO hindamiskomponent_admin USING (hk_private.admin_context('admin_configuration'));
CREATE POLICY admin_insert ON public.kst_configuration_activations FOR INSERT
    TO hindamiskomponent_admin WITH CHECK (hk_private.admin_context('admin_configuration'));

CREATE POLICY admin_select ON public.repo_materjalid FOR SELECT
    TO hindamiskomponent_admin USING (hk_private.admin_context('admin_sources'));
CREATE POLICY admin_insert ON public.repo_materjalid FOR INSERT
    TO hindamiskomponent_admin WITH CHECK (hk_private.admin_context('admin_sources'));
CREATE POLICY worker_select ON public.repo_materjalid FOR SELECT
    TO hindamiskomponent_worker USING (hk_private.worker_context());
CREATE POLICY admin_select ON public.yg_reeglid FOR SELECT
    TO hindamiskomponent_admin USING (hk_private.admin_context('admin_rules'));
CREATE POLICY admin_insert ON public.yg_reeglid FOR INSERT
    TO hindamiskomponent_admin WITH CHECK (hk_private.admin_context('admin_rules'));
CREATE POLICY worker_select ON public.yg_reeglid FOR SELECT
    TO hindamiskomponent_worker USING (hk_private.worker_context());

CREATE POLICY assessment_select ON public.ylesandepank FOR SELECT
    TO hindamiskomponent_app, hindamiskomponent_admin
    USING (hk_private.assessment_context(ARRAY['test_create', 'player_start', 'player_answer', 'player_report']));
CREATE POLICY admin_select ON public.ylesandepank FOR SELECT
    TO hindamiskomponent_admin USING (hk_private.admin_context('admin_items'));
CREATE POLICY admin_insert ON public.ylesandepank FOR INSERT
    TO hindamiskomponent_admin WITH CHECK (hk_private.admin_context('admin_items'));
CREATE POLICY admin_update ON public.ylesandepank FOR UPDATE
    TO hindamiskomponent_admin USING (hk_private.admin_context('admin_items'))
    WITH CHECK (hk_private.admin_context('admin_items'));
CREATE POLICY worker_select ON public.ylesandepank FOR SELECT
    TO hindamiskomponent_worker USING (hk_private.worker_context());
CREATE POLICY worker_insert ON public.ylesandepank FOR INSERT
    TO hindamiskomponent_worker WITH CHECK (hk_private.worker_context());

CREATE POLICY assessment_usage ON public.ylesandepank FOR UPDATE
    TO hindamiskomponent_app, hindamiskomponent_admin USING (
        hk_private.assessment_context(ARRAY['player_answer'])
        AND EXISTS (
            -- Commit ordering: insert the answer, increment usage, then advance
            -- the session in the same transaction. The saved UUID and item must
            -- match the selected active session's current question.
            SELECT FROM public.testisessioonid AS session
            JOIN public.tulemustepank AS answer ON answer.test_id = session.test_id
            WHERE session.test_id = nullif(current_setting('hk.test_id', true), '')
              AND session.staatus = 'aktiivne'
              AND session.tp_seisund #>> '{current_question,item_id}' = ylesandepank.yp_id::text
              AND session.tp_seisund #>> '{current_question,submission_id}' = answer.vastus_id::text
              AND answer.yp_id = ylesandepank.yp_id
        )
    ) WITH CHECK (hk_private.assessment_context(ARRAY['player_answer']));
CREATE POLICY assessment_report ON public.ylesandepank FOR UPDATE
    TO hindamiskomponent_app USING (
        hk_private.assessment_context(ARRAY['player_report'])
        AND EXISTS (
            SELECT FROM public.testisessioonid AS session
            WHERE session.test_id = nullif(current_setting('hk.test_id', true), '')
              AND session.staatus = 'aktiivne'
              AND session.tp_seisund #>> '{current_question,item_id}' = ylesandepank.yp_id::text
        )
    ) WITH CHECK (hk_private.assessment_context(ARRAY['player_report']));

-- Exact grants: no runtime table-wide UPDATE, DELETE, TRUNCATE or REFERENCES.
GRANT SELECT ON public.testisessioonid, public.tulemustepank, public.yg_tellimused,
    public.ylesandepank, public.graafid_kst, public.kst_model_cache,
    public.kst_configuration_versions, public.kst_configuration_activations
    TO hindamiskomponent_app, hindamiskomponent_admin;
GRANT INSERT ON public.testisessioonid, public.graafid_kst, public.kst_model_cache
    TO hindamiskomponent_app, hindamiskomponent_admin;
GRANT INSERT (test_id, yp_id, skoor, valitud_vastus, vastatud_ajal, vastus_id,
    graafi_objekt_snapshot, juhis_snapshot, tyvi_snapshot, stiimul_snapshot, voti_snapshot, arvutuskaik_snapshot)
    ON public.tulemustepank TO hindamiskomponent_app, hindamiskomponent_admin;
GRANT INSERT (test_id, kursus, graafi_objektid, kognitiivne_tase, maht, staatus,
    loodud, ylesande_taotlused, graafi_ema_objekt)
    ON public.yg_tellimused TO hindamiskomponent_app, hindamiskomponent_admin;
GRANT UPDATE (graaf_hash, staatus, lopp_profiil, testi_loogika, tp_seisund)
    ON public.testisessioonid TO hindamiskomponent_app, hindamiskomponent_admin;
GRANT UPDATE (ebaadekvaatne_arv, kasutamiste_arv, viimane_kasutus)
    ON public.ylesandepank TO hindamiskomponent_app;
GRANT UPDATE (juhis, tyvi, stiimul, voti, distraktor_1, distraktor_2, distraktor_3,
    staatus, irt_a, irt_b, beeta_error, g_guess, kasutamiste_arv, viimane_kasutus)
    ON public.ylesandepank TO hindamiskomponent_admin;
GRANT SELECT ON public.repo_materjalid, public.yg_reeglid TO hindamiskomponent_admin;
GRANT INSERT (kursus, pealkiri, allika_url, sisu_tekst, lisatud)
    ON public.repo_materjalid TO hindamiskomponent_admin;
GRANT INSERT (kursus, reegli_kirjeldus, naidis_json) ON public.yg_reeglid TO hindamiskomponent_admin;
GRANT INSERT (schema_version, configuration, configuration_hash, created_by, created_at)
    ON public.kst_configuration_versions TO hindamiskomponent_admin;
GRANT INSERT (configuration_version_id, activated_by, activated_at)
    ON public.kst_configuration_activations TO hindamiskomponent_admin;
GRANT SELECT ON public.yg_tellimused, public.ylesandepank, public.repo_materjalid, public.yg_reeglid
    TO hindamiskomponent_worker;
GRANT UPDATE (staatus, taitmise_tulemus, attempt_count, next_attempt_at,
    locked_until, claim_token, last_error, completed_at)
    ON public.yg_tellimused TO hindamiskomponent_worker;
GRANT INSERT (kursus, graafi_objekt, graafi_ema_objekt, kognitiivne_tase, juhis,
    tyvi, stiimul, voti, distraktor_1, distraktor_2, distraktor_3, skoor,
    irt_a, irt_b, beeta_error, g_guess, staatus, arvutuskaik,
    ebaadekvaatne_arv, kasutamiste_arv, viimane_kasutus)
    ON public.ylesandepank TO hindamiskomponent_admin;
GRANT INSERT (kursus, graafi_objekt, graafi_ema_objekt, kognitiivne_tase, juhis,
    tyvi, stiimul, voti, distraktor_1, distraktor_2, distraktor_3, skoor,
    irt_a, irt_b, beeta_error, g_guess, staatus, arvutuskaik)
    ON public.ylesandepank TO hindamiskomponent_worker;

GRANT USAGE ON SEQUENCE public.tulemustepank_id_seq, public.yg_tellimused_id_seq
    TO hindamiskomponent_app, hindamiskomponent_admin;
GRANT USAGE ON SEQUENCE public.repo_materjalid_id_seq, public.yg_reeglid_id_seq,
    public.kst_configuration_activations_id_seq, public.ylesandepank_yp_id_seq
    TO hindamiskomponent_admin;
GRANT USAGE ON SEQUENCE public.ylesandepank_yp_id_seq TO hindamiskomponent_worker;

REVOKE ALL ON FUNCTION public.increment_ebaadekvaatne_arv(bigint),
    public.increment_ylesande_kasutus(bigint, timestamptz),
    public.reject_kst_configuration_mutation(), public.reject_kst_model_cache_mutation(),
    public.reject_graph_mutation(), public.reject_result_mutation() FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA hk_private FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.increment_ebaadekvaatne_arv(bigint) TO hindamiskomponent_app;
GRANT EXECUTE ON FUNCTION public.increment_ylesande_kasutus(bigint, timestamptz)
    TO hindamiskomponent_app, hindamiskomponent_admin;
GRANT EXECUTE ON FUNCTION hk_private.assessment_context(text[]), hk_private.selected_test(text)
    TO hindamiskomponent_app, hindamiskomponent_admin;
GRANT EXECUTE ON FUNCTION hk_private.admin_context(text) TO hindamiskomponent_admin;
GRANT EXECUTE ON FUNCTION hk_private.worker_context() TO hindamiskomponent_worker;
-- The guard branches by role before calling predicates with narrower EXECUTE
-- grants. Trigger execution itself does not require a runtime EXECUTE grant.

COMMIT;
