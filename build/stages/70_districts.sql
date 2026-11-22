-- Округа: сводная модель по региональным командованиям ВС РК вместо подробной структуры.
-- Идемпотентно (схема district пересоздаётся). Требует этап 60_kz_regional_commands.sql.
--
-- Что откуда берётся:
--   округа (4 учебных округа на месте региональных командований), города штабов, зоны ответственности —
--     refdata.kz_regional_command / kz_rc_region. В учебной базе они называются «Округ …», код ОКР-…;
--     официальные названия РгК остаются только в справочнике refdata;
--     (открытые источники, достоверность A/B, см. этап 60);
--   соединения в составе округа — УСЛОВНЫЕ (C): реальный состав РгК открыто не опубликован;
--   мини-модель «всё по три»: в округе 3 соединения, в соединении 3 батальона, в батальоне 3 роты,
--     в роте 3 взвода, во взводе 3 отделения — УСЛОВНЫЕ (C); подразделений обеспечения нет;
--   численность, техника, обеспеченность — УЧЕБНЫЕ (C): профиль своей бригады (подразделения 20.%)
--     × масштаб соединений; случайности нет, масштабы заданы ниже явно.
-- Данные условного противника (США, подразделения 34.%) в сводную модель НЕ попадают.
-- Подробные таблицы mil_core этим этапом не меняются.
\set ON_ERROR_STOP on
BEGIN;

ALTER TABLE etl.load_run
  ADD COLUMN IF NOT EXISTS stage text, ADD COLUMN IF NOT EXISTS kind text,
  ADD COLUMN IF NOT EXISTS script_name text, ADD COLUMN IF NOT EXISTS note text;

DO $$ BEGIN
  IF to_regclass('refdata.kz_regional_command') IS NULL THEN
    RAISE EXCEPTION 'нет refdata.kz_regional_command: сначала примените build/stages/60_kz_regional_commands.sql';
  END IF;
END $$;

DROP SCHEMA IF EXISTS district CASCADE;
CREATE SCHEMA district;
COMMENT ON SCHEMA district IS
  'Учебная база. Округа — региональные командования ВС РК по открытым источникам; состав соединений, численность, техника и запасы условные (C).';

INSERT INTO etl.load_run (started_at, source_dir, status, stage, kind, script_name, note)
VALUES (clock_timestamp(), 'build/', 'running', '70_districts', 'derived', '70_districts.sql',
        'Сводная модель по учебным округам (на месте РгК ВС РК): справочник refdata.kz_* + профиль бригады 20.% × масштабы условных соединений; данные США не используются');

CREATE TABLE district.district (
  district_code text PRIMARY KEY CHECK (district_code LIKE 'ОКР-%'),
  rc_code       text NOT NULL UNIQUE REFERENCES refdata.kz_regional_command (rc_code),
  short_name    text NOT NULL CHECK (short_name LIKE 'Округ %'),
  full_name     text NOT NULL,
  hq_city       text NOT NULL,
  side          text NOT NULL CHECK (side = 'свои'),
  zone_note     text NOT NULL,
  sort_order    integer NOT NULL,
  stock_factor  numeric NOT NULL,
  is_training   boolean NOT NULL DEFAULT true CHECK (is_training),
  origin        text NOT NULL CHECK (origin IN ('derived', 'generated')),
  confidence    text NOT NULL CHECK (confidence IN ('A', 'B', 'C')),
  load_run_id   bigint NOT NULL REFERENCES etl.load_run);
COMMENT ON COLUMN district.district.rc_code IS 'Код регионального командования в справочнике refdata (источник названия, штаба и зоны)';
COMMENT ON COLUMN district.district.confidence IS 'Достоверность названия, штаба и зоны (по худшему из источников этапа 60); числа по округу всегда C';
COMMENT ON COLUMN district.district.stock_factor IS 'Условная доля наличия запасов относительно базового профиля (C)';

CREATE TABLE district.formation (
  formation_code text PRIMARY KEY,
  district_code  text NOT NULL REFERENCES district.district,
  formation_name text NOT NULL,
  formation_type text NOT NULL,
  scale          numeric NOT NULL CHECK (scale > 0),
  origin         text NOT NULL CHECK (origin IN ('derived', 'generated')),
  load_run_id    bigint NOT NULL REFERENCES etl.load_run);
COMMENT ON TABLE district.formation IS 'Условные соединения в составе округа (C). Реальный состав открыто не опубликован';
COMMENT ON COLUMN district.formation.scale IS 'Масштаб соединения относительно базовой бригады (1.00 = базовая)';

-- Подразделения соединений: батальон (дивизион) -> рота (батарея) -> взвод -> отделение. Все условные (C).
CREATE TABLE district.subunit (
  subunit_code   text PRIMARY KEY,
  formation_code text NOT NULL REFERENCES district.formation,
  parent_code    text REFERENCES district.subunit,
  level          text NOT NULL CHECK (level IN ('управление', 'батальон', 'рота', 'взвод', 'отделение')),
  level_rank     smallint NOT NULL CHECK (level_rank BETWEEN 1 AND 4),
  subunit_name   text NOT NULL,
  norm_kind      text NOT NULL,
  sort_key       integer[] NOT NULL,
  origin         text NOT NULL CHECK (origin = 'generated'),
  confidence     text NOT NULL CHECK (confidence = 'C'),
  load_run_id    bigint NOT NULL REFERENCES etl.load_run,
  CHECK (parent_code IS NOT NULL OR level <> 'отделение'));
CREATE INDEX ON district.subunit (formation_code);
CREATE INDEX ON district.subunit (parent_code);
COMMENT ON TABLE district.subunit IS
  'Условные подразделения соединений (C): типовой шаблон 3 батальона × 3 роты × 3 взвода × 3 отделения, '
  'подразделения обеспечения батальонов и подразделения бригадного подчинения (управление, роты, взводы). '
  'level — общий уровень (батальон/рота/взвод/отделение); в названии — род: дивизион, батарея и т. п.';

-- Типовые нормы (открытые источники): кто служит в подразделении данного вида и что у него есть.
CREATE TABLE district.norm_source (
  source_code text PRIMARY KEY,
  title       text NOT NULL,
  url         text,
  confidence  text NOT NULL CHECK (confidence IN ('A', 'B', 'C')));
COMMENT ON TABLE district.norm_source IS
  'Источники типовых норм. A — факт из открытого источника (экипаж машины), B — типовой состав СА/ВС РФ по открытым '
  'источникам (FM 100-2-3, 1991, через Википедию), C — оценка составителя. Штаты ВС РК не опубликованы.';

CREATE TABLE district.norm_staff (
  kind          text NOT NULL,
  seq           smallint NOT NULL,
  position_name text NOT NULL,
  rank_name     text NOT NULL REFERENCES mil_core.rank,
  qty           smallint NOT NULL CHECK (qty > 0),
  source_code   text NOT NULL REFERENCES district.norm_source,
  PRIMARY KEY (kind, seq));

CREATE TABLE district.norm_equipment (
  kind        text NOT NULL,
  item_sname  text NOT NULL REFERENCES mil_core.item,
  qty         smallint NOT NULL CHECK (qty > 0),
  source_code text NOT NULL REFERENCES district.norm_source,
  PRIMARY KEY (kind, item_sname));

-- Должности и техника каждого подразделения (собственные, без подчинённых) и итоги снизу вверх.
CREATE TABLE district.subunit_staff (
  subunit_code  text NOT NULL REFERENCES district.subunit,
  seq           smallint NOT NULL,
  position_name text NOT NULL,
  rank_name     text NOT NULL REFERENCES mil_core.rank,
  qty           smallint NOT NULL CHECK (qty > 0),
  source_code   text NOT NULL REFERENCES district.norm_source,
  PRIMARY KEY (subunit_code, seq));

CREATE TABLE district.subunit_equipment (
  subunit_code text NOT NULL REFERENCES district.subunit,
  item_sname   text NOT NULL REFERENCES mil_core.item,
  qty          smallint NOT NULL CHECK (qty > 0),
  source_code  text NOT NULL REFERENCES district.norm_source,
  PRIMARY KEY (subunit_code, item_sname));

CREATE TABLE district.subunit_total (
  subunit_code    text PRIMARY KEY REFERENCES district.subunit,
  own_personnel   integer NOT NULL,
  personnel       integer NOT NULL,
  officers        integer NOT NULL,
  sergeants       integer NOT NULL,
  soldiers        integer NOT NULL,
  equipment_units integer NOT NULL);
COMMENT ON TABLE district.subunit_total IS 'Итоги подразделения вместе со всеми подчинёнными (снизу вверх)';

CREATE TABLE district.strength (
  district_code text NOT NULL REFERENCES district.district,
  category      text NOT NULL CHECK (category IN ('офицеры', 'сержанты', 'солдаты')),
  personnel     integer NOT NULL CHECK (personnel >= 0),
  origin        text NOT NULL CHECK (origin IN ('derived', 'generated')),
  confidence    text NOT NULL CHECK (confidence IN ('A', 'B', 'C')),
  load_run_id   bigint NOT NULL REFERENCES etl.load_run,
  PRIMARY KEY (district_code, category));

CREATE TABLE district.equipment (
  district_code text NOT NULL REFERENCES district.district,
  item_sname    text NOT NULL REFERENCES mil_core.item,
  qty           numeric NOT NULL CHECK (qty >= 0),
  origin        text NOT NULL CHECK (origin IN ('derived', 'generated')),
  confidence    text NOT NULL CHECK (confidence IN ('A', 'B', 'C')),
  load_run_id   bigint NOT NULL REFERENCES etl.load_run,
  PRIMARY KEY (district_code, item_sname));

CREATE TABLE district.supply (
  district_code text NOT NULL REFERENCES district.district,
  item_sname    text NOT NULL REFERENCES mil_core.item,
  norm_qty      numeric NOT NULL CHECK (norm_qty >= 0),
  stock_qty     numeric NOT NULL CHECK (stock_qty >= 0),
  origin        text NOT NULL CHECK (origin IN ('derived', 'generated')),
  confidence    text NOT NULL CHECK (confidence IN ('A', 'B', 'C')),
  load_run_id   bigint NOT NULL REFERENCES etl.load_run,
  PRIMARY KEY (district_code, item_sname));

-- ---------------------------------------------------------------- округа (из справочника этапа 60)
-- Учебные названия: «РгК «Восток»» -> «Округ «Восток»», «региональное командование …» -> «учебный округ …»,
-- код РгК-ВОС -> ОКР-ВОС.
INSERT INTO district.district (district_code, rc_code, short_name, full_name, hq_city, side, zone_note, sort_order,
                               stock_factor, origin, confidence, load_run_id)
SELECT replace(c.rc_code, 'РгК-', 'ОКР-'), c.rc_code,
       regexp_replace(c.short_name, '^РгК', 'Округ'),
       regexp_replace(c.full_name, '^региональное командование', 'учебный округ'),
       c.hq_city, 'свои',
       (SELECT string_agg(r.region_name || CASE WHEN r.confidence <> 'A' THEN '*' ELSE '' END, ', '
                          ORDER BY r.region_kind DESC, r.region_name)
          FROM refdata.kz_rc_region r WHERE r.rc_code = c.rc_code)
       || ' (по Указу № 354 от 2012 г., утратил силу в 2018 г.; * — вывод для областей, образованных позже)',
       c.sort_order, f.stock, 'derived',
       greatest(c.hq_confidence, (SELECT max(r.confidence) FROM refdata.kz_rc_region r WHERE r.rc_code = c.rc_code)),
       currval('etl.load_run_run_id_seq')
FROM refdata.kz_regional_command c
JOIN (VALUES ('РгК-АСТ', 0.97), ('РгК-ВОС', 0.88), ('РгК-ЗАП', 0.93), ('РгК-ЮГ', 1.02)) f(code, stock) ON f.code = c.rc_code;

-- ---------------------------------------------------------------- условные соединения
-- ВОС-1 — базовая бригада: в подробной модели 12 мбр входит в РгК «Восток» (узел 20.0.6.), здесь — Округ «Восток».
INSERT INTO district.formation (formation_code, district_code, formation_name, formation_type, scale, origin, load_run_id)
SELECT v.code, v.d, v.name, v.typ, v.scale, v.origin, currval('etl.load_run_run_id_seq')
FROM (VALUES
  ('АСТ-1', 'ОКР-АСТ', 'Условное соединение АСТ-1', 'механизированная бригада (условная)', 1.00, 'generated'),
  ('АСТ-2', 'ОКР-АСТ', 'Условное соединение АСТ-2', 'механизированная бригада (условная)', 0.95, 'generated'),
  ('АСТ-3', 'ОКР-АСТ', 'Условное соединение АСТ-3', 'артиллерийская бригада (условная)', 0.35, 'generated'),
  ('ВОС-1', 'ОКР-ВОС', 'Условное соединение ВОС-1 (профиль 12 мбр)', 'механизированная бригада (условная)', 1.00, 'derived'),
  ('ВОС-2', 'ОКР-ВОС', 'Условное соединение ВОС-2', 'механизированная бригада (условная)', 0.90, 'generated'),
  ('ВОС-3', 'ОКР-ВОС', 'Условное соединение ВОС-3', 'бригада обеспечения (условная)', 0.50, 'generated'),
  ('ЗАП-1', 'ОКР-ЗАП', 'Условное соединение ЗАП-1', 'механизированная бригада (условная)', 1.00, 'generated'),
  ('ЗАП-2', 'ОКР-ЗАП', 'Условное соединение ЗАП-2', 'механизированная бригада (условная)', 0.90, 'generated'),
  ('ЗАП-3', 'ОКР-ЗАП', 'Условное соединение ЗАП-3', 'бригада обеспечения (условная)', 0.80, 'generated'),
  ('ЮГ-1',  'ОКР-ЮГ',  'Условное соединение ЮГ-1',  'механизированная бригада (условная)', 1.10, 'generated'),
  ('ЮГ-2',  'ОКР-ЮГ',  'Условное соединение ЮГ-2',  'механизированная бригада (условная)', 1.00, 'generated'),
  ('ЮГ-3',  'ОКР-ЮГ',  'Условное соединение ЮГ-3',  'танковая бригада (условная)', 0.60, 'generated')
) v(code, d, name, typ, scale, origin);

-- ---------------------------------------------------------------- типовые нормы (открытые источники)
-- Штаты ВС РК не опубликованы. Состав взят из открытых описаний типовых подразделений СА/ВС РФ
-- (FM 100-2-3, 1991, через статьи Википедии) и характеристик машин; звания — по системе ВС РК, как в модели 12 мбр.
INSERT INTO district.norm_source (source_code, title, url, confidence) VALUES
  ('W_MSO',  'Мотострелковое отделение: 9 чел. — экипаж БМП (командир, наводчик-оператор, механик-водитель) и десант 6 (по FM 100-2-3)', 'https://ru.wikipedia.org/wiki/Мотострелковое_отделение', 'B'),
  ('W_MSV',  'Мотострелковый взвод: 28 чел., 3 отделения, командир — младший офицер (СА, конец 1980-х, по FM 100-2-3)', 'https://ru.wikipedia.org/wiki/Мотострелковый_взвод', 'B'),
  ('W_MSR',  'Мотострелковая рота: управление (командир, заместители, техник, старшина) и 3 взвода; 103–110 чел. в СА', 'https://ru.wikipedia.org/wiki/Мотострелковая_рота', 'B'),
  ('W_TV',   'Танковый взвод: 9 чел. в танковом полку СА (3 танка)', 'https://ru.wikipedia.org/wiki/Танковый_взвод', 'B'),
  ('W_TR',   'Танковая рота: управление и 3 танковых взвода; 30 чел. в танковом полку СА', 'https://ru.wikipedia.org/wiki/Танковая_рота', 'B'),
  ('W_T72',  'Т-72: экипаж 3 чел. — командир, наводчик, механик-водитель', 'https://ru.wikipedia.org/wiki/Т-72', 'A'),
  ('W_BMP2', 'БМП-2: экипаж 3 чел., десант 7', 'https://ru.wikipedia.org/wiki/БМП-2', 'A'),
  ('W_2S1',  '2С1 «Гвоздика»: расчёт 4 — командир, наводчик, заряжающий, механик-водитель', 'https://ru.wikipedia.org/wiki/2С1', 'A'),
  ('W_BM21', 'БМ-21 «Град»: расчёт 5 — командир, наводчик, два номера, механик-водитель', 'https://ru.wikipedia.org/wiki/БМ-21', 'A'),
  ('W_BAT',  'Артиллерийская батарея: управление (командир, техник, старшина), взвод управления, огневые взводы; 6 орудий', 'https://ru.wikipedia.org/wiki/Артиллерийская_батарея', 'B'),
  ('EST',    'Оценка составителя по типовой структуре: открытого источника с этими цифрами нет', NULL, 'C');

INSERT INTO district.norm_staff (kind, seq, position_name, rank_name, qty, source_code) VALUES
  -- механизированные подразделения
  ('мех_отделение', 1, 'Командир отделения (командир БМП)', 'сержант третьего класса', 1, 'W_MSO'),
  ('мех_отделение', 2, 'Наводчик-оператор БМП', 'сержант третьего класса', 1, 'W_MSO'),
  ('мех_отделение', 3, 'Механик-водитель БМП', 'рядовой', 1, 'W_MSO'),
  ('мех_отделение', 4, 'Старший стрелок', 'ефрейтор', 1, 'W_MSO'),
  ('мех_отделение', 5, 'Пулемётчик', 'рядовой', 1, 'W_MSO'),
  ('мех_отделение', 6, 'Стрелок-гранатомётчик', 'рядовой', 1, 'W_MSO'),
  ('мех_отделение', 7, 'Помощник гранатомётчика', 'рядовой', 1, 'W_MSO'),
  ('мех_отделение', 8, 'Стрелок', 'рядовой', 2, 'W_MSO'),
  ('мех_взвод', 1, 'Командир механизированного взвода', 'лейтенант', 1, 'W_MSV'),
  ('мех_рота', 1, 'Командир механизированной роты', 'капитан', 1, 'W_MSR'),
  ('мех_рота', 2, 'Заместитель командира роты', 'старший лейтенант', 1, 'W_MSR'),
  ('мех_рота', 3, 'Заместитель командира роты по воспитательной работе', 'старший лейтенант', 1, 'W_MSR'),
  ('мех_рота', 4, 'Техник роты', 'сержант первого класса', 1, 'W_MSR'),
  ('мех_рота', 5, 'Старшина роты', 'сержант первого класса', 1, 'W_MSR'),
  ('мех_рота', 6, 'Санитарный инструктор', 'сержант третьего класса', 1, 'EST'),
  ('мех_рота', 7, 'Наводчик-оператор БМП командира роты', 'сержант третьего класса', 1, 'EST'),
  ('мех_рота', 8, 'Механик-водитель БМП командира роты', 'рядовой', 1, 'EST'),
  ('мех_бат', 1, 'Командир механизированного батальона', 'подполковник', 1, 'EST'),
  ('мех_бат', 2, 'Начальник штаба — заместитель командира батальона', 'майор', 1, 'EST'),
  ('мех_бат', 3, 'Заместитель командира батальона по воспитательной работе', 'майор', 1, 'EST'),
  ('мех_бат', 4, 'Заместитель командира батальона по вооружению', 'майор', 1, 'EST'),
  ('мех_бат', 5, 'Заместитель командира батальона по тылу', 'капитан', 1, 'EST'),
  ('мех_бат', 6, 'Помощник начальника штаба', 'капитан', 1, 'EST'),
  ('мех_бат', 7, 'Наводчик-оператор КШМ командира батальона', 'сержант третьего класса', 1, 'EST'),
  ('мех_бат', 8, 'Механик-водитель КШМ командира батальона', 'рядовой', 1, 'EST'),
  -- танковые подразделения: взвод — 3 танка, у первого командир — командир взвода
  ('танк_экипаж', 1, 'Командир танка', 'сержант третьего класса', 1, 'W_T72'),
  ('танк_экипаж', 2, 'Наводчик', 'ефрейтор', 1, 'W_T72'),
  ('танк_экипаж', 3, 'Механик-водитель', 'рядовой', 1, 'W_T72'),
  ('танк_экипаж_кв', 1, 'Командир танкового взвода (командир танка)', 'лейтенант', 1, 'W_TV'),
  ('танк_экипаж_кв', 2, 'Наводчик', 'ефрейтор', 1, 'W_T72'),
  ('танк_экипаж_кв', 3, 'Механик-водитель', 'рядовой', 1, 'W_T72'),
  ('танк_рота', 1, 'Командир танковой роты (командир танка)', 'капитан', 1, 'W_TR'),
  ('танк_рота', 2, 'Наводчик танка командира роты', 'ефрейтор', 1, 'W_TR'),
  ('танк_рота', 3, 'Механик-водитель танка командира роты', 'рядовой', 1, 'W_TR'),
  ('танк_бат', 1, 'Командир танкового батальона (командир танка)', 'подполковник', 1, 'EST'),
  ('танк_бат', 2, 'Начальник штаба — заместитель командира батальона', 'майор', 1, 'EST'),
  ('танк_бат', 3, 'Заместитель командира батальона по воспитательной работе', 'майор', 1, 'EST'),
  ('танк_бат', 4, 'Заместитель командира батальона по вооружению', 'майор', 1, 'EST'),
  ('танк_бат', 5, 'Заместитель командира батальона по тылу', 'капитан', 1, 'EST'),
  ('танк_бат', 6, 'Наводчик танка командира батальона', 'ефрейтор', 1, 'EST'),
  ('танк_бат', 7, 'Механик-водитель танка командира батальона', 'рядовой', 1, 'EST'),
  -- артиллерия: батарея — 2 огневых взвода по 3 орудия и взвод управления
  ('расчёт_2С1', 1, 'Командир орудия (САУ)', 'сержант третьего класса', 1, 'W_2S1'),
  ('расчёт_2С1', 2, 'Наводчик', 'ефрейтор', 1, 'W_2S1'),
  ('расчёт_2С1', 3, 'Заряжающий', 'рядовой', 1, 'W_2S1'),
  ('расчёт_2С1', 4, 'Механик-водитель', 'рядовой', 1, 'W_2S1'),
  ('расчёт_БМ21', 1, 'Командир боевой машины', 'сержант третьего класса', 1, 'W_BM21'),
  ('расчёт_БМ21', 2, 'Старший наводчик', 'ефрейтор', 1, 'W_BM21'),
  ('расчёт_БМ21', 3, 'Номер расчёта', 'рядовой', 2, 'W_BM21'),
  ('расчёт_БМ21', 4, 'Механик-водитель', 'рядовой', 1, 'W_BM21'),
  ('огневой_взвод', 1, 'Командир огневого взвода', 'лейтенант', 1, 'W_BAT'),
  ('взвод_управления', 1, 'Командир взвода управления', 'лейтенант', 1, 'W_BAT'),
  ('отд_разведки', 1, 'Командир отделения разведки', 'сержант третьего класса', 1, 'EST'),
  ('отд_разведки', 2, 'Разведчик-дальномерщик', 'рядовой', 2, 'EST'),
  ('отд_связи', 1, 'Командир отделения связи', 'сержант третьего класса', 1, 'EST'),
  ('отд_связи', 2, 'Радиотелефонист', 'рядовой', 2, 'EST'),
  ('выч_отделение', 1, 'Старший вычислитель', 'сержант третьего класса', 1, 'EST'),
  ('выч_отделение', 2, 'Вычислитель', 'рядовой', 2, 'EST'),
  ('батарея', 1, 'Командир батареи', 'капитан', 1, 'W_BAT'),
  ('батарея', 2, 'Техник батареи', 'сержант первого класса', 1, 'W_BAT'),
  ('батарея', 3, 'Старшина батареи', 'сержант первого класса', 1, 'W_BAT'),
  ('батарея', 4, 'Санитарный инструктор батареи', 'сержант третьего класса', 1, 'W_BAT'),
  ('арт_дивизион', 1, 'Командир дивизиона', 'подполковник', 1, 'EST'),
  ('арт_дивизион', 2, 'Начальник штаба — заместитель командира дивизиона', 'майор', 1, 'EST'),
  ('арт_дивизион', 3, 'Заместитель командира дивизиона по воспитательной работе', 'майор', 1, 'EST'),
  ('арт_дивизион', 4, 'Заместитель командира дивизиона по вооружению', 'майор', 1, 'EST'),
  ('арт_дивизион', 5, 'Заместитель командира дивизиона по тылу', 'капитан', 1, 'EST'),
  -- подразделения обеспечения (открытых штатов нет — оценка)
  ('авто_отделение', 1, 'Командир автомобильного отделения', 'сержант третьего класса', 1, 'EST'),
  ('авто_отделение', 2, 'Водитель', 'рядовой', 4, 'EST'),
  ('рем_отделение', 1, 'Командир ремонтного отделения', 'сержант третьего класса', 1, 'EST'),
  ('рем_отделение', 2, 'Слесарь-ремонтник', 'рядовой', 3, 'EST'),
  ('отд_подвоза', 1, 'Командир отделения подвоза', 'сержант третьего класса', 1, 'EST'),
  ('отд_подвоза', 2, 'Водитель', 'рядовой', 3, 'EST'),
  ('авто_взвод', 1, 'Командир автомобильного взвода', 'лейтенант', 1, 'EST'),
  ('рем_взвод', 1, 'Командир ремонтного взвода', 'лейтенант', 1, 'EST'),
  ('мто_взвод', 1, 'Командир взвода подвоза', 'лейтенант', 1, 'EST'),
  ('обесп_рота', 1, 'Командир роты', 'капитан', 1, 'EST'),
  ('обесп_рота', 2, 'Заместитель командира роты', 'старший лейтенант', 1, 'EST'),
  ('обесп_рота', 3, 'Старшина роты', 'сержант первого класса', 1, 'EST'),
  ('обесп_бат', 1, 'Командир батальона', 'подполковник', 1, 'EST'),
  ('обесп_бат', 2, 'Начальник штаба — заместитель командира батальона', 'майор', 1, 'EST'),
  ('обесп_бат', 3, 'Заместитель командира батальона по вооружению', 'майор', 1, 'EST'),
  ('обесп_бат', 4, 'Заместитель командира батальона по тылу', 'капитан', 1, 'EST');

-- Должности сержантов-инструкторов из Устава внутренней службы ВС РК (через лист «Должности и звания»
-- рабочей книги «Штатные_должности_численность_имущество_2026.xlsx»). Источник подтверждает название и
-- обязанности, но не звание: звание — оценка составителя. В танковых взводах не добавляются (все места — экипажи).
INSERT INTO district.norm_source (source_code, title, url, confidence) VALUES
  ('UKAZ_364', 'Устав внутренней службы ВС РК (Указ № 364 от 05.07.2007, обновлённый текст): сержанты батальона, '
               'роты и взвода — инструкторы по боевой и физической подготовке; звание источник не устанавливает (оценка)',
   'https://old.adilet.zan.kz/rus/docs/U070000364_', 'B');
INSERT INTO district.norm_staff (kind, seq, position_name, rank_name, qty, source_code)
SELECT k.kind, (SELECT max(n.seq) FROM district.norm_staff n WHERE n.kind = k.kind) + 1, k.pos, k.rank_name, 1, 'UKAZ_364'
FROM (VALUES
  ('мех_бат',          'Сержант батальона — инструктор по боевой и физической подготовке', 'штаб-сержант'),
  ('танк_бат',         'Сержант батальона — инструктор по боевой и физической подготовке', 'штаб-сержант'),
  ('обесп_бат',        'Сержант батальона — инструктор по боевой и физической подготовке', 'штаб-сержант'),
  ('арт_дивизион',     'Сержант дивизиона — инструктор по боевой и физической подготовке', 'штаб-сержант'),
  ('мех_рота',         'Сержант роты — инструктор по боевой и физической подготовке', 'сержант первого класса'),
  ('танк_рота',        'Сержант роты — инструктор по боевой и физической подготовке', 'сержант первого класса'),
  ('обесп_рота',       'Сержант роты — инструктор по боевой и физической подготовке', 'сержант первого класса'),
  ('батарея',          'Сержант батареи — инструктор по боевой и физической подготовке', 'сержант первого класса'),
  ('мех_взвод',        'Сержант взвода — инструктор по боевой и физической подготовке (заместитель командира взвода)', 'сержант второго класса'),
  ('огневой_взвод',    'Сержант взвода — инструктор по боевой и физической подготовке (заместитель командира взвода)', 'сержант второго класса'),
  ('взвод_управления', 'Сержант взвода — инструктор по боевой и физической подготовке (заместитель командира взвода)', 'сержант второго класса'),
  ('мто_взвод',        'Сержант взвода — инструктор по боевой и физической подготовке (заместитель командира взвода)', 'сержант второго класса'),
  ('рем_взвод',        'Сержант взвода — инструктор по боевой и физической подготовке (заместитель командира взвода)', 'сержант второго класса'),
  ('авто_взвод',       'Сержант взвода — инструктор по боевой и физической подготовке (заместитель командира взвода)', 'сержант второго класса')
) k(kind, pos, rank_name);

INSERT INTO district.norm_equipment (kind, item_sname, qty, source_code) VALUES
  ('мех_отделение', 'БМП-2', 1, 'W_MSO'),
  ('мех_отделение', 'РПГ-7Д', 1, 'W_MSO'),
  ('мех_отделение', '7,62-мм ПКМ', 1, 'W_MSO'),
  ('мех_отделение', '5,45-мм АК-74М', 5, 'EST'),
  ('мех_отделение', '5,45-мм АКС-74У', 2, 'EST'),
  ('мех_взвод', '5,45-мм АК-74М', 1, 'EST'),
  ('мех_взвод', 'Р-168-0,5У', 1, 'EST'),
  ('мех_рота', 'БМП-2', 1, 'EST'),
  ('мех_рота', '9-мм ПМ', 3, 'EST'),
  ('мех_рота', '5,45-мм АК-74М', 3, 'EST'),
  ('мех_рота', '5,45-мм АКС-74У', 2, 'EST'),
  ('мех_бат', 'БМП-1КШ', 1, 'EST'),
  ('мех_бат', 'УАЗ-3151', 1, 'EST'),
  ('мех_бат', '9-мм ПМ', 6, 'EST'),
  ('мех_бат', '5,45-мм АКС-74У', 2, 'EST'),
  ('танк_экипаж', 'Т-72Б', 1, 'W_TV'),
  ('танк_экипаж', '5,45-мм АКС-74У', 3, 'EST'),
  ('танк_экипаж_кв', 'Т-72Б', 1, 'W_TV'),
  ('танк_экипаж_кв', '9-мм ПМ', 1, 'EST'),
  ('танк_экипаж_кв', '5,45-мм АКС-74У', 2, 'EST'),
  ('танк_рота', 'Т-72К', 1, 'W_TR'),
  ('танк_рота', '9-мм ПМ', 1, 'EST'),
  ('танк_рота', '5,45-мм АКС-74У', 2, 'EST'),
  ('танк_бат', 'Т-72К', 1, 'EST'),
  ('танк_бат', 'УАЗ-3151', 1, 'EST'),
  ('танк_бат', '9-мм ПМ', 5, 'EST'),
  ('танк_бат', '5,45-мм АКС-74У', 2, 'EST'),
  ('расчёт_2С1', '122-мм 2С1 Гвоздика', 1, 'W_2S1'),
  ('расчёт_2С1', '5,45-мм АКС-74У', 4, 'EST'),
  ('расчёт_БМ21', 'БМ-21 РСЗО Град', 1, 'W_BM21'),
  ('расчёт_БМ21', '5,45-мм АКС-74У', 5, 'EST'),
  ('огневой_взвод', '9-мм ПМ', 1, 'EST'),
  ('взвод_управления', '9-мм ПМ', 1, 'EST'),
  ('взвод_управления', 'МТ-ЛБУ', 1, 'EST'),
  ('отд_разведки', '5,45-мм АКС-74У', 3, 'EST'),
  ('отд_связи', 'Р-168-0,5У', 2, 'EST'),
  ('отд_связи', '5,45-мм АКС-74У', 3, 'EST'),
  ('выч_отделение', '5,45-мм АКС-74У', 3, 'EST'),
  ('батарея', '9-мм ПМ', 1, 'EST'),
  ('батарея', '5,45-мм АК-74М', 3, 'EST'),
  ('арт_дивизион', 'УАЗ-3151', 1, 'EST'),
  ('арт_дивизион', '9-мм ПМ', 5, 'EST'),
  ('авто_отделение', 'УРАЛ-4320', 4, 'EST'),
  ('авто_отделение', '5,45-мм АКС-74У', 5, 'EST'),
  ('рем_отделение', 'МТО-АТ', 1, 'EST'),
  ('рем_отделение', '5,45-мм АКС-74У', 4, 'EST'),
  ('отд_подвоза', 'АТМЗ-5-4320', 1, 'EST'),
  ('отд_подвоза', 'УРАЛ-4320', 2, 'EST'),
  ('отд_подвоза', '5,45-мм АКС-74У', 4, 'EST'),
  ('авто_взвод', '9-мм ПМ', 1, 'EST'),
  ('рем_взвод', '9-мм ПМ', 1, 'EST'),
  ('мто_взвод', '9-мм ПМ', 1, 'EST'),
  ('обесп_рота', '9-мм ПМ', 2, 'EST'),
  ('обесп_рота', '5,45-мм АК-74М', 1, 'EST'),
  ('обесп_рота', 'УАЗ-3151', 1, 'EST'),
  ('обесп_бат', '9-мм ПМ', 4, 'EST'),
  ('обесп_бат', 'УАЗ-3151', 1, 'EST');

-- ---------------------------------------------------------------- подразделения соединений (шаблон, C)
-- Для каждого типа соединения — три батальона своего рода (bk). Роты нумеруются сквозь соединение (1–9),
-- взводы — внутри роты (1–3), отделения — внутри взвода (1–3). Номер роты в коде тот же, что в названии:
-- «8-я танковая рота» = ВОС-1.Б3.Р8. norm_kind — по какой типовой норме заполняется подразделение.
CREATE TEMP TABLE zz_bn_template ON COMMIT DROP AS
SELECT * FROM (VALUES
  ('механизированная бригада', 1, 'мех',   '1-й механизированный батальон',          'механизированная рота'),
  ('механизированная бригада', 2, 'мех',   '2-й механизированный батальон',          'механизированная рота'),
  ('механизированная бригада', 3, 'танк',  'танковый батальон',                      'танковая рота'),
  ('танковая бригада',         1, 'танк',  '1-й танковый батальон',                  'танковая рота'),
  ('танковая бригада',         2, 'танк',  '2-й танковый батальон',                  'танковая рота'),
  ('танковая бригада',         3, 'мех',   'механизированный батальон',              'механизированная рота'),
  ('артиллерийская бригада',   1, 'гауб',  '1-й гаубичный артиллерийский дивизион', 'гаубичная батарея'),
  ('артиллерийская бригада',   2, 'гауб',  '2-й гаубичный артиллерийский дивизион', 'гаубичная батарея'),
  ('артиллерийская бригада',   3, 'реакт', 'реактивный артиллерийский дивизион',     'реактивная батарея'),
  ('бригада обеспечения',      1, 'мто',   'батальон материального обеспечения',     'рота материального обеспечения'),
  ('бригада обеспечения',      2, 'рем',   'ремонтно-восстановительный батальон',     'ремонтная рота'),
  ('бригада обеспечения',      3, 'авто',  'автомобильный батальон',                 'автомобильная рота')
) t(kind, bn, bk, bn_name, company_kind);

CREATE TEMP TABLE zz_bn ON COMMIT DROP AS
SELECT f.formation_code, t.bn, t.bk, t.bn_name, t.company_kind
FROM district.formation f
JOIN zz_bn_template t ON f.formation_type LIKE t.kind || '%';

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM district.formation f WHERE NOT EXISTS (SELECT 1 FROM zz_bn b WHERE b.formation_code = f.formation_code)) THEN
    RAISE EXCEPTION 'для типа соединения нет шаблона батальонов';
  END IF;
END $$;

-- все узлы шаблона со своим видом и названием
CREATE TEMP TABLE zz_node ON COMMIT DROP AS
SELECT b.formation_code, b.bn, b.bk, b.bn_name, b.company_kind, r, v, o
FROM zz_bn b CROSS JOIN generate_series(1, 3) r CROSS JOIN generate_series(1, 3) v CROSS JOIN generate_series(1, 3) o;

INSERT INTO district.subunit (subunit_code, formation_code, parent_code, level, level_rank, subunit_name, norm_kind, sort_key, origin, confidence, load_run_id)
SELECT DISTINCT formation_code || '.Б' || bn, formation_code, NULL::text, 'батальон', 1, bn_name,
       CASE bk WHEN 'мех' THEN 'мех_бат' WHEN 'танк' THEN 'танк_бат' WHEN 'гауб' THEN 'арт_дивизион'
               WHEN 'реакт' THEN 'арт_дивизион' ELSE 'обесп_бат' END,
       ARRAY[bn], 'generated', 'C', currval('etl.load_run_run_id_seq')
FROM zz_node;

INSERT INTO district.subunit (subunit_code, formation_code, parent_code, level, level_rank, subunit_name, norm_kind, sort_key, origin, confidence, load_run_id)
SELECT DISTINCT formation_code || '.Б' || bn || '.Р' || ((bn - 1) * 3 + r), formation_code, formation_code || '.Б' || bn,
       'рота', 2, ((bn - 1) * 3 + r) || '-я ' || company_kind,
       CASE bk WHEN 'мех' THEN 'мех_рота' WHEN 'танк' THEN 'танк_рота' WHEN 'гауб' THEN 'батарея'
               WHEN 'реакт' THEN 'батарея' ELSE 'обесп_рота' END,
       ARRAY[bn, r], 'generated', 'C', currval('etl.load_run_run_id_seq')
FROM zz_node;

INSERT INTO district.subunit (subunit_code, formation_code, parent_code, level, level_rank, subunit_name, norm_kind, sort_key, origin, confidence, load_run_id)
SELECT DISTINCT formation_code || '.Б' || bn || '.Р' || ((bn - 1) * 3 + r) || '.В' || v, formation_code,
       formation_code || '.Б' || bn || '.Р' || ((bn - 1) * 3 + r), 'взвод', 3,
       CASE WHEN bk = 'мех' THEN v || '-й механизированный взвод'
            WHEN bk = 'танк' THEN v || '-й танковый взвод'
            WHEN bk IN ('гауб', 'реакт') AND v < 3 THEN v || '-й огневой взвод'
            WHEN bk IN ('гауб', 'реакт') THEN 'взвод управления'
            WHEN bk = 'авто' THEN v || '-й автомобильный взвод'
            WHEN bk = 'рем' THEN v || '-й ремонтный взвод'
            ELSE v || '-й взвод подвоза' END,
       CASE WHEN bk = 'мех' THEN 'мех_взвод' WHEN bk = 'танк' THEN 'танк_взвод'
            WHEN bk IN ('гауб', 'реакт') AND v < 3 THEN 'огневой_взвод'
            WHEN bk IN ('гауб', 'реакт') THEN 'взвод_управления'
            WHEN bk = 'авто' THEN 'авто_взвод' WHEN bk = 'рем' THEN 'рем_взвод' ELSE 'мто_взвод' END,
       ARRAY[bn, r, v], 'generated', 'C', currval('etl.load_run_run_id_seq')
FROM zz_node;

INSERT INTO district.subunit (subunit_code, formation_code, parent_code, level, level_rank, subunit_name, norm_kind, sort_key, origin, confidence, load_run_id)
SELECT formation_code || '.Б' || bn || '.Р' || ((bn - 1) * 3 + r) || '.В' || v || '.О' || o, formation_code,
       formation_code || '.Б' || bn || '.Р' || ((bn - 1) * 3 + r) || '.В' || v, 'отделение', 4,
       CASE WHEN bk = 'мех' THEN o || '-е механизированное отделение'
            WHEN bk = 'танк' AND o = 1 THEN '1-й экипаж (танк командира взвода)'
            WHEN bk = 'танк' THEN o || '-й экипаж'
            WHEN bk = 'гауб' AND v < 3 THEN ((v - 1) * 3 + o) || '-е орудие (расчёт САУ 2С1)'
            WHEN bk = 'реакт' AND v < 3 THEN ((v - 1) * 3 + o) || '-я боевая машина (расчёт БМ-21)'
            WHEN bk IN ('гауб', 'реакт') THEN (ARRAY['отделение разведки', 'отделение связи', 'вычислительное отделение'])[o]
            WHEN bk = 'авто' THEN o || '-е автомобильное отделение'
            WHEN bk = 'рем' THEN o || '-е ремонтное отделение'
            ELSE o || '-е отделение подвоза' END,
       CASE WHEN bk = 'мех' THEN 'мех_отделение'
            WHEN bk = 'танк' AND o = 1 THEN 'танк_экипаж_кв'
            WHEN bk = 'танк' THEN 'танк_экипаж'
            WHEN bk = 'гауб' AND v < 3 THEN 'расчёт_2С1'
            WHEN bk = 'реакт' AND v < 3 THEN 'расчёт_БМ21'
            WHEN bk IN ('гауб', 'реакт') THEN (ARRAY['отд_разведки', 'отд_связи', 'выч_отделение'])[o]
            WHEN bk = 'авто' THEN 'авто_отделение' WHEN bk = 'рем' THEN 'рем_отделение' ELSE 'отд_подвоза' END,
       ARRAY[bn, r, v, o], 'generated', 'C', currval('etl.load_run_run_id_seq')
FROM zz_node;

-- ---------------------------------------------------------------- должности и техника по нормам
INSERT INTO district.subunit_staff (subunit_code, seq, position_name, rank_name, qty, source_code)
SELECT s.subunit_code, n.seq, n.position_name, n.rank_name, n.qty, n.source_code
FROM district.subunit s JOIN district.norm_staff n ON n.kind = s.norm_kind;

INSERT INTO district.subunit_equipment (subunit_code, item_sname, qty, source_code)
SELECT s.subunit_code, n.item_sname, n.qty, n.source_code
FROM district.subunit s JOIN district.norm_equipment n ON n.kind = s.norm_kind;

-- итоги подразделения вместе с подчинёнными: код подчинённого начинается с кода старшего и точки
INSERT INTO district.subunit_total
SELECT s.subunit_code,
       coalesce((SELECT sum(qty) FROM district.subunit_staff x WHERE x.subunit_code = s.subunit_code), 0),
       coalesce(sum(st.qty), 0),
       coalesce(sum(st.qty) FILTER (WHERE r.category = 'офицеры'), 0),
       coalesce(sum(st.qty) FILTER (WHERE r.category = 'сержанты'), 0),
       coalesce(sum(st.qty) FILTER (WHERE r.category = 'солдаты'), 0),
       coalesce((SELECT sum(e.qty) FROM district.subunit_equipment e JOIN mil_core.item i USING (item_sname)
                  WHERE (e.subunit_code = s.subunit_code OR e.subunit_code LIKE s.subunit_code || '.%')
                    AND i.category <> 'Стрелковое оружие и гранатомёты'), 0)
FROM district.subunit s
LEFT JOIN district.subunit_staff st ON st.subunit_code = s.subunit_code OR st.subunit_code LIKE s.subunit_code || '.%'
LEFT JOIN mil_core.rank r ON r.rank_name = st.rank_name
GROUP BY s.subunit_code;

-- ---------------------------------------------------------------- базовый профиль запасов: только своя бригада (20.%)
CREATE TEMP TABLE zz_base_strength ON COMMIT DROP AS
SELECT count(*)::int AS n
FROM mil_core.staff_position s JOIN mil_core.unit u USING (unit_code)
WHERE u.side = 'свои';

CREATE TEMP TABLE zz_base_supply ON COMMIT DROP AS
SELECT v.item_sname, sum(v.norm_qty) AS norm_qty, sum(greatest(coalesce(v.balance, 0), 0)) AS stock_qty
FROM mil_core.v_stock_vs_norm v JOIN mil_core.warehouse w USING (warehouse_id) JOIN mil_core.unit u ON u.unit_code = w.unit_code
WHERE w.kind <> 'вышестоящий' AND u.side = 'свои'
GROUP BY 1;

-- ---------------------------------------------------------------- итоги округов снизу вверх
-- Численность и техника округа = сумма его подразделений. Запасы: профиль норм 12 мбр, пересчитанный
-- на численность округа (норма на человека та же), наличие — с учётом условной доли stock_factor.
INSERT INTO district.strength
SELECT f.district_code, r.category, sum(st.qty)::int, 'derived', 'C', currval('etl.load_run_run_id_seq')
FROM district.subunit_staff st JOIN district.subunit s USING (subunit_code)
JOIN district.formation f USING (formation_code) JOIN mil_core.rank r USING (rank_name)
GROUP BY f.district_code, r.category;

INSERT INTO district.equipment
SELECT f.district_code, e.item_sname, sum(e.qty), 'derived', 'C', currval('etl.load_run_run_id_seq')
FROM district.subunit_equipment e JOIN district.subunit s USING (subunit_code) JOIN district.formation f USING (formation_code)
GROUP BY f.district_code, e.item_sname;

CREATE TEMP TABLE zz_scale ON COMMIT DROP AS
SELECT d.district_code, d.stock_factor,
       (SELECT sum(personnel) FROM district.strength x WHERE x.district_code = d.district_code)::numeric
         / (SELECT n FROM zz_base_strength) AS scale
FROM district.district d;

INSERT INTO district.supply
SELECT s.district_code, b.item_sname, greatest(1, round(b.norm_qty * s.scale)), round(b.stock_qty * s.scale * s.stock_factor),
       'generated', 'C', currval('etl.load_run_run_id_seq')
FROM zz_scale s CROSS JOIN zz_base_supply b
WHERE b.norm_qty > 0;

DO $$ BEGIN
  IF (SELECT count(*) FROM district.district) <> 4 THEN RAISE EXCEPTION 'ожидалось 4 округа'; END IF;
  IF EXISTS (SELECT 1 FROM district.formation GROUP BY district_code HAVING count(*) <> 3) THEN
    RAISE EXCEPTION 'в каждом округе должно быть 3 соединения';
  END IF;
  IF (SELECT count(*) FROM district.subunit WHERE subunit_code ~ '\.Б\d(\.Р\d(\.В\d(\.О\d)?)?)?$')
     <> 120 * (SELECT count(*) FROM district.formation) THEN
    RAISE EXCEPTION 'в каждом соединении должно быть 120 подразделений (3 + 9 + 27 + 81)';
  END IF;
  IF (SELECT count(*) FROM district.subunit) <> 120 * (SELECT count(*) FROM district.formation) THEN
    RAISE EXCEPTION 'есть подразделения вне сетки «всё по три»';
  END IF;
  IF EXISTS (SELECT 1 FROM district.subunit s WHERE s.level = 'отделение'
             AND NOT EXISTS (SELECT 1 FROM district.subunit_staff x WHERE x.subunit_code = s.subunit_code)) THEN
    RAISE EXCEPTION 'есть отделение без должностей: проверьте нормы district.norm_staff';
  END IF;
  IF (SELECT sum(personnel) FROM district.strength) <> (SELECT sum(qty) FROM district.subunit_staff) THEN
    RAISE EXCEPTION 'численность округов не равна сумме подразделений';
  END IF;
  IF EXISTS (SELECT 1 FROM district.equipment e JOIN mil_core.item i USING (item_sname) WHERE i.country = 'США') THEN
    RAISE EXCEPTION 'в сводную модель попала техника США';
  END IF;
END $$;

UPDATE etl.load_run SET finished_at = clock_timestamp(), status = 'ok',
       stats = jsonb_build_object('loaded', jsonb_build_object(
         'district', (SELECT count(*) FROM district.district), 'formation', (SELECT count(*) FROM district.formation),
         'subunit', (SELECT count(*) FROM district.subunit),
         'subunit_staff', (SELECT count(*) FROM district.subunit_staff),
         'subunit_equipment', (SELECT count(*) FROM district.subunit_equipment),
         'strength', (SELECT count(*) FROM district.strength), 'equipment', (SELECT count(*) FROM district.equipment),
         'supply', (SELECT count(*) FROM district.supply)))
 WHERE run_id = currval('etl.load_run_run_id_seq');

-- ---------------------------------------------------------------- представления для Django (только чтение)
CREATE OR REPLACE VIEW registry_api.districts AS
SELECT d.district_code, d.short_name, d.full_name, d.side, d.zone_note, d.sort_order, d.origin, d.confidence,
       (SELECT count(*) FROM district.formation f WHERE f.district_code = d.district_code) AS formations,
       (SELECT coalesce(sum(personnel), 0) FROM district.strength s WHERE s.district_code = d.district_code) AS personnel_total,
       (SELECT count(*) FROM district.equipment e WHERE e.district_code = d.district_code) AS equipment_items,
       (SELECT coalesce(sum(qty), 0) FROM district.equipment e WHERE e.district_code = d.district_code) AS equipment_units,
       (SELECT round(100 * avg(least(stock_qty / norm_qty, 1)), 1) FROM district.supply p
         WHERE p.district_code = d.district_code AND p.norm_qty > 0) AS supply_pct,
       'учебные данные'::text AS data_status,
       d.hq_city
FROM district.district d;

CREATE OR REPLACE VIEW registry_api.district_regions AS
SELECT d.district_code, r.region_name, r.region_kind, r.confidence, r.basis, r.as_of,
       s.title AS source_title, s.url AS source_url
FROM refdata.kz_rc_region r JOIN refdata.kz_rc_source s USING (source_code)
JOIN district.district d ON d.rc_code = r.rc_code;

CREATE OR REPLACE VIEW registry_api.district_formations AS
SELECT f.formation_code, f.district_code, f.formation_name, f.formation_type, f.scale, f.origin,
       'учебные данные'::text AS data_status,
       count(*) FILTER (WHERE s.level = 'батальон') AS battalions,
       count(*) FILTER (WHERE s.level = 'рота') AS companies,
       count(*) FILTER (WHERE s.level = 'взвод') AS platoons,
       count(*) FILTER (WHERE s.level = 'отделение') AS squads,
       coalesce(sum(t.personnel) FILTER (WHERE s.parent_code IS NULL), 0) AS personnel,
       coalesce(sum(t.officers) FILTER (WHERE s.parent_code IS NULL), 0) AS officers,
       coalesce(sum(t.sergeants) FILTER (WHERE s.parent_code IS NULL), 0) AS sergeants,
       coalesce(sum(t.soldiers) FILTER (WHERE s.parent_code IS NULL), 0) AS soldiers,
       coalesce(sum(t.equipment_units) FILTER (WHERE s.parent_code IS NULL), 0) AS equipment_units
FROM district.formation f LEFT JOIN district.subunit s USING (formation_code)
LEFT JOIN district.subunit_total t USING (subunit_code)
GROUP BY f.formation_code;

CREATE OR REPLACE VIEW registry_api.district_subunits AS
SELECT s.subunit_code, s.formation_code, f.district_code, s.parent_code, s.level, s.level_rank, s.subunit_name,
       s.norm_kind, s.sort_key, s.origin, s.confidence, 'учебные данные'::text AS data_status,
       t.own_personnel, t.personnel, t.officers, t.sergeants, t.soldiers, t.equipment_units
FROM district.subunit s JOIN district.formation f USING (formation_code) JOIN district.subunit_total t USING (subunit_code);

CREATE OR REPLACE VIEW registry_api.subunit_staff AS
SELECT st.subunit_code, s.formation_code, f.district_code, st.seq, st.position_name, st.rank_name, r.category, st.qty,
       st.source_code, ns.title AS source_title, ns.url AS source_url, ns.confidence, 'учебные данные'::text AS data_status
FROM district.subunit_staff st JOIN district.subunit s USING (subunit_code) JOIN district.formation f USING (formation_code)
JOIN mil_core.rank r USING (rank_name) JOIN district.norm_source ns USING (source_code);

CREATE OR REPLACE VIEW registry_api.subunit_equipment AS
SELECT e.subunit_code, s.formation_code, f.district_code, e.item_sname, i.item_name, i.category, e.qty, i.unit_measure,
       e.source_code, ns.title AS source_title, ns.url AS source_url, ns.confidence, 'учебные данные'::text AS data_status
FROM district.subunit_equipment e JOIN district.subunit s USING (subunit_code) JOIN district.formation f USING (formation_code)
JOIN mil_core.item i USING (item_sname) JOIN district.norm_source ns USING (source_code);

CREATE OR REPLACE VIEW registry_api.norm_sources AS
SELECT source_code, title, url, confidence FROM district.norm_source;

CREATE OR REPLACE VIEW registry_api.district_strength AS
SELECT district_code, category, personnel, origin, confidence, 'учебные данные'::text AS data_status
FROM district.strength;

CREATE OR REPLACE VIEW registry_api.district_equipment AS
SELECT e.district_code, e.item_sname, i.item_name, i.category, e.qty, i.unit_measure, e.origin, e.confidence,
       'учебные данные'::text AS data_status
FROM district.equipment e JOIN mil_core.item i USING (item_sname);

CREATE OR REPLACE VIEW registry_api.district_supply AS
SELECT p.district_code, p.item_sname, i.item_name, i.category, p.norm_qty, p.stock_qty,
       greatest(p.norm_qty - p.stock_qty, 0) AS deficit,
       CASE WHEN p.norm_qty > 0 THEN round(100 * p.stock_qty / p.norm_qty, 1) END AS provision_pct,
       i.unit_measure, p.origin, p.confidence, 'учебные данные'::text AS data_status
FROM district.supply p JOIN mil_core.item i USING (item_sname);

CREATE OR REPLACE VIEW registry_api.item_specs AS
SELECT s.item_sname, s.param_name, s.value_num, s.value_text, pr.unit, s.confidence, s.source_code, src.source_name, s.note
FROM mil_core.item_spec s LEFT JOIN mil_core.param pr USING (param_name) LEFT JOIN mil_core.source src USING (source_code);

CREATE OR REPLACE VIEW registry_api.item_aliases AS
SELECT alias, item_sname FROM mil_core.item_alias;

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'registry_reader') THEN
    GRANT SELECT ON ALL TABLES IN SCHEMA registry_api TO registry_reader;
  END IF;
END $$;

COMMIT;

SELECT district_code, short_name, hq_city, formations, personnel_total, equipment_items, equipment_units, supply_pct, confidence
FROM registry_api.districts ORDER BY sort_order;
