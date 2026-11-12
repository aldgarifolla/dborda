-- =====================================================================
--  Схема PostgreSQL для данных из Excel-выгрузок «Военной БД»
--  (brigade_все_данные.xlsx + military_db_v2_обзор.xlsx).
--  ПРЕДЛОЖЕНИЕ НА СОГЛАСОВАНИЕ: отдельные схемы, основную модель проекта не трогает.
--  PostgreSQL 13+.
--
--  Принцип: в mil_core лежат только первичные факты (кто, что, где, сколько своё).
--  Всё «с подчинёнными» (численность, потребность, техника, горючее, БК по уровням)
--  считается представлениями v_* и сверяется с соответствующими листами Excel.
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS etl;
CREATE SCHEMA IF NOT EXISTS excel_stage;
CREATE SCHEMA IF NOT EXISTS mil_core;

-- ------------------------------------------------------------------ ETL
CREATE TABLE IF NOT EXISTS etl.load_run (
    run_id BIGSERIAL PRIMARY KEY, started_at TIMESTAMPTZ NOT NULL DEFAULT now(), finished_at TIMESTAMPTZ,
    source_dir TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','ok','failed')), stats JSONB);
CREATE TABLE IF NOT EXISTS etl.reject (
    reject_id BIGSERIAL PRIMARY KEY, run_id BIGINT NOT NULL REFERENCES etl.load_run ON DELETE CASCADE,
    entity TEXT NOT NULL, severity TEXT NOT NULL CHECK (severity IN ('error','warning','info')),
    src_file TEXT, src_sheet TEXT, src_row INTEGER, reason TEXT NOT NULL, raw JSONB);
CREATE TABLE IF NOT EXISTS etl.reconcile (
    run_id BIGINT NOT NULL REFERENCES etl.load_run ON DELETE CASCADE,
    check_name TEXT NOT NULL, excel_sheet TEXT NOT NULL, rows_compared INTEGER NOT NULL,
    rows_equal INTEGER NOT NULL, rows_diff INTEGER NOT NULL, only_in_excel INTEGER NOT NULL, only_in_db INTEGER NOT NULL,
    note TEXT, PRIMARY KEY (run_id, check_name));

-- ------------------------------------------------------------------ STAGE: каждая строка каждого листа как есть
CREATE TABLE IF NOT EXISTS excel_stage.raw_row (
    run_id BIGINT NOT NULL REFERENCES etl.load_run ON DELETE CASCADE,
    src_file TEXT NOT NULL, src_sheet TEXT NOT NULL, src_row INTEGER NOT NULL, data JSONB NOT NULL,
    PRIMARY KEY (run_id, src_file, src_sheet, src_row));

-- ------------------------------------------------------------------ CORE: справочники
CREATE TABLE IF NOT EXISTS mil_core.source (
    source_code TEXT PRIMARY KEY, source_name TEXT NOT NULL UNIQUE, publisher TEXT, url TEXT,
    source_type TEXT, license TEXT, accessed_on DATE);
CREATE TABLE IF NOT EXISTS mil_core.unit_level (level_id INTEGER PRIMARY KEY, level_name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS mil_core.rank (
    rank_name TEXT PRIMARY KEY, category TEXT NOT NULL CHECK (category IN ('солдаты','сержанты','прапорщики','офицеры')),
    army TEXT NOT NULL CHECK (army IN ('РФ','США')), sort_order INTEGER);
CREATE TABLE IF NOT EXISTS mil_core.position (position_name TEXT PRIMARY KEY, army TEXT NOT NULL CHECK (army IN ('РФ','США')));
CREATE TABLE IF NOT EXISTS mil_core.item (
    item_sname TEXT PRIMARY KEY, item_name TEXT NOT NULL UNIQUE, category TEXT NOT NULL,
    country TEXT, unit_measure TEXT NOT NULL, legacy_id INTEGER UNIQUE);
CREATE TABLE IF NOT EXISTS mil_core.kit (kit_code TEXT PRIMARY KEY, kit_name TEXT NOT NULL UNIQUE, army TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mil_core.kit_item (
    kit_code TEXT REFERENCES mil_core.kit, item_sname TEXT REFERENCES mil_core.item, qty INTEGER NOT NULL CHECK (qty > 0),
    PRIMARY KEY (kit_code, item_sname));
CREATE TABLE IF NOT EXISTS mil_core.position_kit (
    position_name TEXT REFERENCES mil_core.position, kit_code TEXT REFERENCES mil_core.kit, PRIMARY KEY (position_name, kit_code));
CREATE TABLE IF NOT EXISTS mil_core.param (param_name TEXT PRIMARY KEY, unit TEXT);
CREATE TABLE IF NOT EXISTS mil_core.country (country_en TEXT PRIMARY KEY, country_ru TEXT);

-- ------------------------------------------------------------------ CORE: структура и люди
CREATE TABLE IF NOT EXISTS mil_core.unit (
    unit_code   TEXT PRIMARY KEY CHECK (unit_code ~ '^(\d+\.)+$'),
    parent_code TEXT REFERENCES mil_core.unit DEFERRABLE INITIALLY DEFERRED,
    short_name  TEXT NOT NULL, full_name TEXT,
    level_name  TEXT REFERENCES mil_core.unit_level(level_name),
    country     TEXT NOT NULL CHECK (country IN ('РФ','США')),
    side        TEXT NOT NULL CHECK (side IN ('свои','противник')),
    confidence  CHAR(1) CHECK (confidence IN ('A','B','C')),
    personnel_own INTEGER NOT NULL DEFAULT 0 CHECK (personnel_own >= 0),          -- своя численность без подчинённых
    personnel_own_estimated INTEGER NOT NULL DEFAULT 0 CHECK (personnel_own_estimated >= 0),
    sort_order  INTEGER,
    depth       INTEGER GENERATED ALWAYS AS (length(unit_code) - length(replace(unit_code, '.', ''))) STORED);
CREATE INDEX IF NOT EXISTS ix_unit_parent ON mil_core.unit(parent_code);
CREATE INDEX IF NOT EXISTS ix_unit_prefix ON mil_core.unit(unit_code text_pattern_ops);

CREATE TABLE IF NOT EXISTS mil_core.person (
    person_id INTEGER PRIMARY KEY, last_name TEXT NOT NULL, first_name TEXT, patronymic TEXT);

CREATE TABLE IF NOT EXISTS mil_core.staff_position (
    staff_id      SERIAL PRIMARY KEY,
    unit_code     TEXT NOT NULL REFERENCES mil_core.unit,
    seq           INTEGER NOT NULL,                       -- порядок в штате подразделения
    position_name TEXT NOT NULL REFERENCES mil_core.position,
    rank_name     TEXT NOT NULL REFERENCES mil_core.rank,
    person_id     INTEGER UNIQUE REFERENCES mil_core.person,
    UNIQUE (unit_code, seq));
CREATE INDEX IF NOT EXISTS ix_staff_unit ON mil_core.staff_position(unit_code);

-- ------------------------------------------------------------------ CORE: техника
CREATE TABLE IF NOT EXISTS mil_core.item_spec (
    spec_id SERIAL PRIMARY KEY, item_sname TEXT NOT NULL REFERENCES mil_core.item, param_name TEXT NOT NULL REFERENCES mil_core.param,
    value_num NUMERIC, value_text TEXT, confidence CHAR(1) NOT NULL CHECK (confidence IN ('A','B','C')),
    source_code TEXT NOT NULL REFERENCES mil_core.source, note TEXT,
    CHECK (value_num IS NOT NULL OR value_text IS NOT NULL));
CREATE TABLE IF NOT EXISTS mil_core.vehicle_crew_role (
    vehicle_sname TEXT REFERENCES mil_core.item, role_name TEXT, qty INTEGER NOT NULL CHECK (qty > 0),
    seat TEXT NOT NULL CHECK (seat IN ('экипаж','десант')), PRIMARY KEY (vehicle_sname, role_name));
CREATE TABLE IF NOT EXISTS mil_core.vehicle_ammo_load (
    vehicle_sname TEXT REFERENCES mil_core.item, ammo_sname TEXT REFERENCES mil_core.item, qty INTEGER NOT NULL CHECK (qty > 0),
    confidence CHAR(1) NOT NULL, PRIMARY KEY (vehicle_sname, ammo_sname));
CREATE TABLE IF NOT EXISTS mil_core.holding (                     -- собственное ВВТ подразделения (без подчинённых)
    unit_code TEXT REFERENCES mil_core.unit, item_sname TEXT REFERENCES mil_core.item,
    qty INTEGER NOT NULL CHECK (qty >= 0), derived_from TEXT NOT NULL, PRIMARY KEY (unit_code, item_sname));
CREATE TABLE IF NOT EXISTS mil_core.crew_assignment (
    staff_id INTEGER PRIMARY KEY REFERENCES mil_core.staff_position ON DELETE CASCADE,
    vehicle_sname TEXT NOT NULL REFERENCES mil_core.item, vehicle_no INTEGER NOT NULL CHECK (vehicle_no > 0),
    seat TEXT NOT NULL CHECK (seat IN ('экипаж','десант')));

-- ------------------------------------------------------------------ CORE: страны
CREATE TABLE IF NOT EXISTS mil_core.milex (
    country_en TEXT REFERENCES mil_core.country, year INTEGER CHECK (year BETWEEN 1900 AND 2100),
    milex_usd_2019 NUMERIC, share_gdp_pct NUMERIC, per_capita_usd NUMERIC, PRIMARY KEY (country_en, year));
CREATE TABLE IF NOT EXISTS mil_core.country_forces (            -- последние значения численности ВС (IISS/World Bank, COW)
    country_en TEXT PRIMARY KEY REFERENCES mil_core.country, af_year INTEGER, armed_forces_personnel NUMERIC,
    cow_milper_thousands NUMERIC);

-- ------------------------------------------------------------------ ПРЕДСТАВЛЕНИЯ (укрупнение по иерархии)
CREATE OR REPLACE VIEW mil_core.v_unit_tree AS
SELECT p.unit_code AS root_code, c.unit_code
FROM mil_core.unit p JOIN mil_core.unit c ON c.unit_code LIKE p.unit_code || '%';

CREATE OR REPLACE VIEW mil_core.v_unit_personnel AS
SELECT t.root_code AS unit_code, SUM(u.personnel_own) AS personnel, SUM(u.personnel_own_estimated) AS personnel_estimated
FROM mil_core.v_unit_tree t JOIN mil_core.unit u ON u.unit_code = t.unit_code GROUP BY t.root_code;

CREATE OR REPLACE VIEW mil_core.v_unit_staff_by_category AS
SELECT t.root_code AS unit_code, COUNT(*) AS staff_total,
       COUNT(*) FILTER (WHERE r.category='офицеры') AS officers, COUNT(*) FILTER (WHERE r.category='прапорщики') AS warrant,
       COUNT(*) FILTER (WHERE r.category='сержанты') AS sergeants, COUNT(*) FILTER (WHERE r.category='солдаты') AS soldiers
FROM mil_core.v_unit_tree t JOIN mil_core.staff_position s ON s.unit_code = t.unit_code JOIN mil_core.rank r USING (rank_name)
GROUP BY t.root_code;

CREATE OR REPLACE VIEW mil_core.v_unit_need AS              -- имущество по табелю положенности
SELECT t.root_code AS unit_code, ki.item_sname, SUM(ki.qty) AS qty
FROM mil_core.v_unit_tree t JOIN mil_core.staff_position s ON s.unit_code = t.unit_code
JOIN mil_core.position_kit pk USING (position_name) JOIN mil_core.kit_item ki USING (kit_code)
GROUP BY t.root_code, ki.item_sname;

CREATE OR REPLACE VIEW mil_core.v_unit_holding AS           -- ВВТ с подчинёнными
SELECT t.root_code AS unit_code, h.item_sname, SUM(h.qty) AS qty
FROM mil_core.v_unit_tree t JOIN mil_core.holding h ON h.unit_code = t.unit_code
GROUP BY t.root_code, h.item_sname;

CREATE OR REPLACE VIEW mil_core.v_item_fuel AS              -- одна заправка: «топливо всего», иначе «баки основные»
SELECT i.item_sname,
       COALESCE((SELECT value_num FROM mil_core.item_spec s WHERE s.item_sname=i.item_sname AND s.param_name='Топливо всего (внутр.+наружн.)' ORDER BY confidence LIMIT 1),
                (SELECT value_num FROM mil_core.item_spec s WHERE s.item_sname=i.item_sname AND s.param_name='Ёмкость топливных баков (основных)' ORDER BY confidence LIMIT 1)) AS refill_l,
       (SELECT value_text FROM mil_core.item_spec s WHERE s.item_sname=i.item_sname AND s.param_name='Вид топлива' ORDER BY confidence LIMIT 1) AS fuel_type
FROM mil_core.item i;

CREATE OR REPLACE VIEW mil_core.v_unit_fuel AS
SELECT h.unit_code, COALESCE(f.fuel_type,'вид не указан') AS fuel_type, SUM(h.qty) AS vehicles,
       SUM(h.qty) FILTER (WHERE f.refill_l IS NOT NULL) AS vehicles_with_data, SUM(h.qty * COALESCE(f.refill_l,0)) AS fuel_one_refill_l
FROM mil_core.v_unit_holding h JOIN mil_core.v_item_fuel f USING (item_sname)
JOIN mil_core.item i USING (item_sname)
WHERE i.category IN ('Бронетанковое вооружение и техника','Автомобильная техника и прицепы','Инженерная техника')
   OR (i.category = 'Ракетно-артиллерийское вооружение' AND EXISTS (SELECT 1 FROM mil_core.item_spec s WHERE s.item_sname=i.item_sname))
   OR f.refill_l IS NOT NULL
GROUP BY h.unit_code, COALESCE(f.fuel_type,'вид не указан');

CREATE OR REPLACE VIEW mil_core.v_unit_ammo AS              -- носимый (табель) + возимый (техника) БК
SELECT unit_code, ammo_sname, SUM(personal) AS personal_load, SUM(vehicle) AS vehicle_load, SUM(personal + vehicle) AS total
FROM (
  SELECT n.unit_code, n.item_sname AS ammo_sname, n.qty AS personal, 0 AS vehicle
  FROM mil_core.v_unit_need n JOIN mil_core.item i USING (item_sname) WHERE i.category = 'Боеприпасы'
  UNION ALL
  SELECT h.unit_code, a.ammo_sname, 0, h.qty * a.qty FROM mil_core.v_unit_holding h JOIN mil_core.vehicle_ammo_load a ON a.vehicle_sname = h.item_sname
) x GROUP BY unit_code, ammo_sname;
