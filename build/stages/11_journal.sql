-- Журнал этапов сборки и учёт изменений строк. Идемпотентно.
-- etl.load_run создан этапом 10 (дамп import_mil.py) и содержит одну запись о загрузке из Excel.
\set ON_ERROR_STOP on
ALTER TABLE etl.load_run
  ADD COLUMN IF NOT EXISTS stage          text,
  ADD COLUMN IF NOT EXISTS kind           text,
  ADD COLUMN IF NOT EXISTS script_name    text,
  ADD COLUMN IF NOT EXISTS script_sha256  text,
  ADD COLUMN IF NOT EXISTS inputs         jsonb,
  ADD COLUMN IF NOT EXISTS counts_before  jsonb,
  ADD COLUMN IF NOT EXISTS counts_after   jsonb,
  ADD COLUMN IF NOT EXISTS row_changes    jsonb,
  ADD COLUMN IF NOT EXISTS note           text;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'load_run_kind_check') THEN
    ALTER TABLE etl.load_run ADD CONSTRAINT load_run_kind_check
      CHECK (kind IS NULL OR kind IN ('import','derived','generated','manual','schema'));
  END IF;
END $$;
COMMENT ON COLUMN etl.load_run.stage IS 'Имя этапа сборки (build/run_all.sh)';
COMMENT ON COLUMN etl.load_run.kind IS 'import — загрузка из исходного файла; derived — расчёт из загруженного; generated — данные созданы скриптом; manual — ручные действия; schema — только структура';
COMMENT ON COLUMN etl.load_run.script_sha256 IS 'SHA-256 файла скрипта этапа';
COMMENT ON COLUMN etl.load_run.inputs IS 'Входные файлы этапа: [{"name":…, "sha256":…, "size_bytes":…}]';
COMMENT ON COLUMN etl.load_run.counts_before IS 'Число строк по таблицам mil_core и refdata до этапа';
COMMENT ON COLUMN etl.load_run.counts_after IS 'Число строк по таблицам mil_core и refdata после этапа';
COMMENT ON COLUMN etl.load_run.row_changes IS 'Сколько строк mil_core этап добавил, изменил и удалил, по таблицам';

-- Рабочая таблица сборки: какая запись журнала создала строку и какая последней её изменила.
-- Ключ строки — текст первичного ключа. Таблица удаляется этапом 62 после переноса в колонки.
CREATE TABLE IF NOT EXISTS etl.row_log (
  table_name  text NOT NULL,
  row_key     text NOT NULL,
  row_hash    text NOT NULL,
  created_run bigint NOT NULL,
  changed_run bigint,
  PRIMARY KEY (table_name, row_key));

CREATE OR REPLACE FUNCTION etl.table_counts() RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE r record; n bigint; out jsonb := '{}';
BEGIN
  FOR r IN SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE c.relkind = 'r' AND n.nspname IN ('mil_core', 'refdata') ORDER BY 1, 2 LOOP
    EXECUTE format('SELECT count(*) FROM %I.%I', r.nspname, r.relname) INTO n;
    out := out || jsonb_build_object(r.nspname || '.' || r.relname, n);
  END LOOP;
  RETURN out;
END $$;

CREATE OR REPLACE FUNCTION etl.pk_expr(p_table regclass) RETURNS text LANGUAGE sql STABLE AS $$
  SELECT 'row(' || string_agg(quote_ident(a.attname), ',' ORDER BY x.n) || ')::text'
  FROM pg_constraint c CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY x(attnum, n)
  JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = x.attnum
  WHERE c.contype = 'p' AND c.conrelid = p_table $$;

-- Сравнивает текущее содержимое таблиц mil_core с etl.row_log и приписывает изменения этапу p_run.
CREATE OR REPLACE FUNCTION etl.track_rows(p_run bigint) RETURNS jsonb LANGUAGE plpgsql AS $$
DECLARE r record; k text; ins bigint; upd bigint; del bigint; out jsonb := '{}';
BEGIN
  IF to_regclass('etl.row_log') IS NULL THEN RETURN NULL; END IF;
  FOR r IN SELECT c.oid::regclass AS t, c.relname FROM pg_class c
           WHERE c.relkind = 'r' AND c.relnamespace = 'mil_core'::regnamespace ORDER BY c.relname LOOP
    k := etl.pk_expr(r.t);
    IF k IS NULL THEN RAISE EXCEPTION 'у таблицы % нет первичного ключа', r.t; END IF;
    EXECUTE format('CREATE TEMP TABLE zz_cur ON COMMIT DROP AS SELECT %s AS k, md5(t::text) AS h FROM %s t', k, r.t);
    DELETE FROM etl.row_log l WHERE l.table_name = r.relname AND NOT EXISTS (SELECT 1 FROM zz_cur c WHERE c.k = l.row_key);
    GET DIAGNOSTICS del = ROW_COUNT;
    UPDATE etl.row_log l SET row_hash = c.h, changed_run = p_run FROM zz_cur c
     WHERE l.table_name = r.relname AND l.row_key = c.k AND l.row_hash <> c.h;
    GET DIAGNOSTICS upd = ROW_COUNT;
    INSERT INTO etl.row_log (table_name, row_key, row_hash, created_run)
    SELECT r.relname, c.k, c.h, p_run FROM zz_cur c
     WHERE NOT EXISTS (SELECT 1 FROM etl.row_log l WHERE l.table_name = r.relname AND l.row_key = c.k);
    GET DIAGNOSTICS ins = ROW_COUNT;
    DROP TABLE zz_cur;
    IF ins + upd + del > 0 THEN
      out := out || jsonb_build_object(r.relname, jsonb_build_object('added', ins, 'changed', upd, 'deleted', del));
    END IF;
  END LOOP;
  RETURN out;
END $$;

CREATE OR REPLACE FUNCTION etl.run_begin(p_stage text, p_kind text, p_script text, p_sha text, p_inputs jsonb, p_note text)
RETURNS bigint LANGUAGE sql AS $$
  INSERT INTO etl.load_run (started_at, source_dir, status, stage, kind, script_name, script_sha256, inputs, counts_before, note)
  VALUES (clock_timestamp(), 'build/', 'running', p_stage, p_kind, p_script, p_sha, p_inputs, etl.table_counts(), p_note)
  RETURNING run_id $$;

CREATE OR REPLACE FUNCTION etl.run_end(p_run bigint) RETURNS void LANGUAGE sql AS $$
  UPDATE etl.load_run SET finished_at = clock_timestamp(), status = 'ok',
         counts_after = etl.table_counts(), row_changes = etl.track_rows(p_run)
   WHERE run_id = p_run $$;
