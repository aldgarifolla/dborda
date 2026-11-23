-- Округа: сводная модель по региональным командованиям ВС РК вместо подробной структуры.
-- Идемпотентно (схема district пересоздаётся вместе с личным составом). Требует этап 60_kz_regional_commands.sql.
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
  origin         text NOT NULL CHECK (origin IN ('derived', 'generated')),
  load_run_id    bigint NOT NULL REFERENCES etl.load_run);
COMMENT ON TABLE district.formation IS 'Условные соединения в составе округа (C). Реальный состав открыто не опубликован';

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
       -- зона ответственности — просто список областей и городов (источники остаются в refdata.kz_rc_region)
       (SELECT string_agg(r.region_name, ', ' ORDER BY r.region_kind DESC, r.region_name)
          FROM refdata.kz_rc_region r WHERE r.rc_code = c.rc_code),
       c.sort_order, f.stock, 'derived',
       greatest(c.hq_confidence, (SELECT max(r.confidence) FROM refdata.kz_rc_region r WHERE r.rc_code = c.rc_code)),
       currval('etl.load_run_run_id_seq')
FROM refdata.kz_regional_command c
JOIN (VALUES ('РгК-АСТ', 0.97), ('РгК-ВОС', 0.88), ('РгК-ЗАП', 0.93), ('РгК-ЮГ', 1.02)) f(code, stock) ON f.code = c.rc_code;

-- ---------------------------------------------------------------- условные соединения
-- ВОС-1 — базовая бригада: в подробной модели 12 мбр входит в РгК «Восток» (узел 20.0.6.), здесь — Округ «Восток».
-- Простые учебные названия со сквозной нумерацией по стране: Астана 1–3, Восток 4–6, Запад 7–9, Юг 10–12.
INSERT INTO district.formation (formation_code, district_code, formation_name, formation_type, origin, load_run_id)
SELECT v.code, v.d, v.name, v.typ, v.origin, currval('etl.load_run_run_id_seq')
FROM (VALUES
  ('АСТ-1', 'ОКР-АСТ', '1-я механизированная бригада',  'механизированная бригада', 'generated'),
  ('АСТ-2', 'ОКР-АСТ', '2-я механизированная бригада',  'механизированная бригада', 'generated'),
  ('АСТ-3', 'ОКР-АСТ', '3-я артиллерийская бригада',    'артиллерийская бригада',   'generated'),
  ('ВОС-1', 'ОКР-ВОС', '4-я механизированная бригада',  'механизированная бригада', 'derived'),
  ('ВОС-2', 'ОКР-ВОС', '5-я механизированная бригада',  'механизированная бригада', 'generated'),
  ('ВОС-3', 'ОКР-ВОС', '6-я бригада обеспечения',       'бригада обеспечения',      'generated'),
  ('ЗАП-1', 'ОКР-ЗАП', '7-я механизированная бригада',  'механизированная бригада', 'generated'),
  ('ЗАП-2', 'ОКР-ЗАП', '8-я механизированная бригада',  'механизированная бригада', 'generated'),
  ('ЗАП-3', 'ОКР-ЗАП', '9-я бригада обеспечения',       'бригада обеспечения',      'generated'),
  ('ЮГ-1',  'ОКР-ЮГ',  '10-я механизированная бригада', 'механизированная бригада', 'generated'),
  ('ЮГ-2',  'ОКР-ЮГ',  '11-я механизированная бригада', 'механизированная бригада', 'generated'),
  ('ЮГ-3',  'ОКР-ЮГ',  '12-я танковая бригада',         'танковая бригада',         'generated')
) v(code, d, name, typ, origin);

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
-- Численность и техника округа = сумма его подразделений. Запасы — ниже, по тому, кто их расходует.
INSERT INTO district.strength
SELECT f.district_code, r.category, sum(st.qty)::int, 'derived', 'C', currval('etl.load_run_run_id_seq')
FROM district.subunit_staff st JOIN district.subunit s USING (subunit_code)
JOIN district.formation f USING (formation_code) JOIN mil_core.rank r USING (rank_name)
GROUP BY f.district_code, r.category;

INSERT INTO district.equipment
SELECT f.district_code, e.item_sname, sum(e.qty), 'derived', 'C', currval('etl.load_run_run_id_seq')
FROM district.subunit_equipment e JOIN district.subunit s USING (subunit_code) JOIN district.formation f USING (formation_code)
GROUP BY f.district_code, e.item_sname;

-- Запасы округа привязаны к тому, кто их расходует (учебная оценка, C):
--   боеприпасы  — боекомплект на единицу оружия × сколько этого оружия в округе (нет оружия — нет и боеприпасов);
--   горючее     — заправка на машину × число машин; масла и охлаждающая жидкость — тоже по машинам;
--   шлемофоны и комбинезоны — по экипажам;
--   одежда, снаряжение, медицина, питание — по численности (норма на человека из профиля 12 мбр).
-- Наличие = норма × доля наличия этой позиции в профиле 12 мбр × условная доля округа stock_factor.
CREATE TEMP TABLE zz_rule ON COMMIT DROP AS
SELECT * FROM (VALUES
  ('5.45-мм ПС (7Н6)',            '5,45-мм АК-74М', 300), ('5.45-мм ПС (7Н6)', '5,45-мм АКС-74У', 300),
  ('7.62-мм ЛПС (57-Н-323С)',     '7,62-мм ПКМ', 1000), ('7.62-мм ЛПС (57-Н-323С)', 'БМП-2', 2000),
  ('7.62-мм ЛПС (57-Н-323С)',     'Т-72Б', 2000), ('7.62-мм ЛПС (57-Н-323С)', 'Т-72К', 2000),
  ('9-мм П (57-Н-181)',           '9-мм ПМ', 16),
  ('12,7-мм Б-32 (57-Б3-542)',    'Т-72Б', 300), ('12,7-мм Б-32 (57-Б3-542)', 'Т-72К', 300),
  ('30-мм выстрелы к 2А42 (БК)',  'БМП-2', 500),
  ('ПТУР 9М111',                  'БМП-2', 4),
  ('125-мм выстрелы к 2А46 (БК)', 'Т-72Б', 45), ('125-мм выстрелы к 2А46 (БК)', 'Т-72К', 45),
  ('122-мм выстрелы к 2А31 (БК)', '122-мм 2С1 Гвоздика', 40),
  ('122-мм М-21ОФ',               'БМ-21 РСЗО Град', 80),
  ('ПГ-7ВС',                      'РПГ-7Д', 5),
  -- запас оружия — 5 % от состоящего на вооружении
  ('5,45-мм АК-74М', '5,45-мм АК-74М', 0.05), ('5,45-мм АКС-74У', '5,45-мм АКС-74У', 0.05),
  ('9-мм ПМ', '9-мм ПМ', 0.05), ('РПГ-7Д', 'РПГ-7Д', 0.05),
  -- горючее: заправка машины, л
  ('ДТ', 'Т-72Б', 1200), ('ДТ', 'Т-72К', 1200), ('ДТ', 'БМП-2', 460), ('ДТ', 'БМП-1КШ', 460),
  ('ДТ', '122-мм 2С1 Гвоздика', 550), ('ДТ', 'БМ-21 РСЗО Град', 360), ('ДТ', 'УРАЛ-4320', 300),
  ('ДТ', 'АТМЗ-5-4320', 300), ('ДТ', 'МТО-АТ', 210), ('ДТ', 'МТ-ЛБУ', 450),
  ('АИ-92', 'УАЗ-3151', 78),
  ('М-10ДМ', 'Т-72Б', 40), ('М-10ДМ', 'Т-72К', 40), ('М-10ДМ', 'БМП-2', 25), ('М-10ДМ', 'БМП-1КШ', 25),
  ('М-10ДМ', '122-мм 2С1 Гвоздика', 25), ('М-10ДМ', 'БМ-21 РСЗО Град', 20), ('М-10ДМ', 'УРАЛ-4320', 20),
  ('М-10ДМ', 'АТМЗ-5-4320', 20), ('М-10ДМ', 'МТО-АТ', 20), ('М-10ДМ', 'МТ-ЛБУ', 25), ('М-10ДМ', 'УАЗ-3151', 6),
  ('ТАп-15В', 'Т-72Б', 20), ('ТАп-15В', 'Т-72К', 20), ('ТАп-15В', 'БМП-2', 15), ('ТАп-15В', 'БМП-1КШ', 15),
  ('ТАп-15В', '122-мм 2С1 Гвоздика', 15), ('ТАп-15В', 'УРАЛ-4320', 12), ('ТАп-15В', 'АТМЗ-5-4320', 12),
  ('ТАп-15В', 'БМ-21 РСЗО Град', 12), ('ТАп-15В', 'МТО-АТ', 12), ('ТАп-15В', 'МТ-ЛБУ', 15), ('ТАп-15В', 'УАЗ-3151', 4),
  ('ОЖ-40', 'Т-72Б', 90), ('ОЖ-40', 'Т-72К', 90), ('ОЖ-40', 'БМП-2', 40), ('ОЖ-40', 'БМП-1КШ', 40),
  ('ОЖ-40', '122-мм 2С1 Гвоздика', 40), ('ОЖ-40', 'УРАЛ-4320', 30), ('ОЖ-40', 'АТМЗ-5-4320', 30),
  ('ОЖ-40', 'БМ-21 РСЗО Град', 30), ('ОЖ-40', 'МТО-АТ', 30), ('ОЖ-40', 'МТ-ЛБУ', 35), ('ОЖ-40', 'УАЗ-3151', 12),
  -- экипажи
  ('Шлемофон ТШ-5', 'Т-72Б', 3), ('Шлемофон ТШ-5', 'Т-72К', 3), ('Шлемофон ТШ-5', 'БМП-2', 3),
  ('Шлемофон ТШ-5', 'БМП-1КШ', 3), ('Шлемофон ТШ-5', '122-мм 2С1 Гвоздика', 4), ('Шлемофон ТШ-5', 'МТ-ЛБУ', 2),
  ('Комбинезон танковый', 'Т-72Б', 3), ('Комбинезон танковый', 'Т-72К', 3),
  ('Комбинезон технический', 'УРАЛ-4320', 1), ('Комбинезон технический', 'АТМЗ-5-4320', 1),
  ('Комбинезон технический', 'МТО-АТ', 2), ('Комбинезон технический', 'БМ-21 РСЗО Град', 1),
  ('Комбинезон технический', 'УАЗ-3151', 1), ('Комбинезон технический', 'МТ-ЛБУ', 1)
) r(item_sname, driver, per_unit);

-- позиции, которые считаются по численности: всё из профиля, кроме привязанных к технике и кроме
-- боеприпасов и оружия без своего оружия в модели (патроны к «Шилке», ракеты «Стрелы-10» и т. п.)
CREATE TEMP TABLE zz_per_person ON COMMIT DROP AS
SELECT b.item_sname, b.norm_qty / (SELECT n FROM zz_base_strength) AS per_person
FROM zz_base_supply b JOIN mil_core.item i USING (item_sname)
WHERE b.norm_qty > 0
  AND b.item_sname NOT IN (SELECT item_sname FROM zz_rule)
  AND i.category NOT IN ('Боеприпасы', 'Стрелковое оружие и гранатомёты')
UNION ALL
SELECT i.item_sname, 2.0 / 1 FROM mil_core.item i WHERE i.item_sname IN ('РГД-5', 'Ф-1');   -- по 2 гранаты на человека

CREATE TEMP TABLE zz_supply_norm ON COMMIT DROP AS
SELECT e.district_code, r.item_sname, sum(e.qty * r.per_unit) AS norm_qty
FROM zz_rule r JOIN district.equipment e ON e.item_sname = r.driver
GROUP BY 1, 2
UNION ALL
SELECT d.district_code, p.item_sname, p.per_person * (SELECT sum(personnel) FROM district.strength x WHERE x.district_code = d.district_code)
FROM district.district d CROSS JOIN zz_per_person p;

INSERT INTO district.supply
SELECT n.district_code, n.item_sname, greatest(1, ceil(n.norm_qty)),
       round(greatest(1, ceil(n.norm_qty))
             * least(1, coalesce(b.stock_qty / nullif(b.norm_qty, 0), 0.8)) * d.stock_factor),
       'generated', 'C', currval('etl.load_run_run_id_seq')
FROM zz_supply_norm n
JOIN district.district d USING (district_code)
LEFT JOIN zz_base_supply b USING (item_sname)
WHERE n.norm_qty > 0;

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
SELECT f.formation_code, f.district_code, f.formation_name, f.formation_type, f.origin,
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

-- ======================================================================== личный состав
-- Личный состав округов: вымышленные люди на штатных местах модели «всё по три».
-- Часть этапа 70: в той же транзакции, что и подразделения, — пересборка не может оставить места без людей.
--
-- Откуда люди:
--   reused    — «свои» военнослужащие из исходного архива (mil_core.person + person_profile, синтетические по README
--               архива). Берутся по категории звания (солдаты / сержанты / офицеры), старшие по возрасту — на старшие
--               звания. Свои ФИО, дата рождения, национальность, анкета и личный номер сохраняются.
--   generated — недостающие места. ФИО собираются из фамилий, имён и отчеств людей архива той же национальности,
--               национальность — по долям архива, возраст, вид службы и образование — по званию (см. zz_age ниже).
-- Все данные ВЫМЫШЛЕННЫЕ (C). ИИН не создаётся: формат настоящего ИИН мог бы совпасть с номером реального человека.
-- Генератор детерминирован (setseed), повторный запуск даёт тех же людей.
DROP VIEW IF EXISTS registry_api.subunit_people;
DROP TABLE IF EXISTS district.person_post;
DROP TABLE IF EXISTS district.person;

CREATE TABLE district.person (
  person_id        integer PRIMARY KEY,
  personal_number  text NOT NULL UNIQUE,
  last_name        text NOT NULL,
  first_name       text NOT NULL,
  patronymic       text,
  sex              char(1) NOT NULL CHECK (sex IN ('М', 'Ж')),
  birth_date       date NOT NULL,
  nationality      text NOT NULL,
  birthplace       text,
  service_type     text NOT NULL CHECK (service_type IN ('срочная воинская служба', 'по контракту')),
  service_start    date NOT NULL,
  contract_end     date,
  education        text,
  marital_status   text,
  children         smallint NOT NULL DEFAULT 0,
  height_cm        smallint,
  weight_kg        smallint,
  blood_group      text,
  fitness_category text,
  origin           text NOT NULL CHECK (origin IN ('reused', 'generated')),
  legacy_person_id integer UNIQUE,
  confidence       char(1) NOT NULL DEFAULT 'C' CHECK (confidence = 'C'));
COMMENT ON TABLE district.person IS 'Вымышленные военнослужащие учебных округов (C). reused — из исходного архива, generated — догенерированы';

CREATE TABLE district.person_post (
  subunit_code text NOT NULL,
  seq          smallint NOT NULL,
  seat         smallint NOT NULL CHECK (seat > 0),
  person_id    integer NOT NULL UNIQUE REFERENCES district.person,
  PRIMARY KEY (subunit_code, seq, seat),
  FOREIGN KEY (subunit_code, seq) REFERENCES district.subunit_staff (subunit_code, seq));
COMMENT ON TABLE district.person_post IS 'Кто занимает штатное место: должность subunit_staff (подразделение, seq) и номер места seat';

SELECT setseed(0.2026);

-- ---------------------------------------------------------------- места: каждая единица qty — отдельное место
CREATE TEMP TABLE zz_seat ON COMMIT DROP AS
SELECT s.subunit_code, s.seq, g.seat, s.rank_name, r.category, r.sort_order
FROM district.subunit_staff s
JOIN mil_core.rank r USING (rank_name)
CROSS JOIN LATERAL generate_series(1, s.qty) g(seat);

-- ---------------------------------------------------------------- люди архива («свои», армия РК)
CREATE TEMP TABLE zz_old ON COMMIT DROP AS
SELECT p.last_name, p.first_name, p.patronymic, pp.*, r.category
FROM mil_core.person p
JOIN mil_core.person_profile pp USING (person_id)
JOIN mil_core.staff_position sp USING (person_id)
JOIN mil_core.rank r ON r.rank_name = sp.rank_name AND r.army = 'РК';

-- старшие по возрасту — на старшие звания внутри категории. Сержантские звания модели — контрактные
-- («сержант третьего класса» и выше), поэтому срочники архива идут только на солдатские места.
CREATE TEMP TABLE zz_match ON COMMIT DROP AS
SELECT s.subunit_code, s.seq, s.seat, o.person_id AS legacy_id
-- внутри одного звания места перемешаны (детерминированно, по md5 кода), чтобы люди архива были во всех округах
FROM (SELECT *, row_number() OVER (PARTITION BY category ORDER BY sort_order DESC, md5(subunit_code || '/' || seq || '/' || seat)) rn
      FROM zz_seat) s
JOIN (SELECT person_id, category, row_number() OVER (PARTITION BY category ORDER BY birth_date, person_id) rn
      FROM zz_old
      WHERE (category = 'солдаты' OR service_type = 'по контракту')
        AND NOT (service_type = 'срочная воинская служба' AND age(date '2026-11-01', birth_date) > interval '27 years')) o
  ON o.category = s.category AND o.rn = s.rn;

-- ---------------------------------------------------------------- пулы для генерации, по национальностям архива
CREATE TEMP TABLE zz_nat ON COMMIT DROP AS
SELECT nationality, n, sum(n) OVER (ORDER BY nationality) AS cum, sum(n) OVER () AS total, ln, fn, pn, bp
FROM (SELECT nationality, count(*)::numeric n,
             array_agg(DISTINCT last_name) ln, array_agg(DISTINCT first_name) fn,
             array_agg(DISTINCT patronymic) FILTER (WHERE patronymic IS NOT NULL) pn,
             array_agg(DISTINCT birthplace) FILTER (WHERE birthplace IS NOT NULL) bp
      FROM zz_old GROUP BY nationality) x;

-- возраст по званию на 01.11.2026 (лет, от–до) и доля срочников среди солдат
CREATE TEMP TABLE zz_age ON COMMIT DROP AS
SELECT * FROM (VALUES
  ('рядовой', 18, 27), ('ефрейтор', 19, 28),
  ('младший сержант', 20, 30), ('сержант', 20, 32), ('старший сержант', 22, 35),
  ('сержант третьего класса', 21, 33), ('сержант второго класса', 24, 38), ('сержант первого класса', 27, 42),
  ('штаб-сержант', 32, 46), ('мастер-сержант', 38, 50),
  ('лейтенант', 22, 25), ('старший лейтенант', 24, 28), ('капитан', 27, 34), ('майор', 32, 40),
  ('подполковник', 37, 45), ('полковник', 42, 50)
) a(rank_name, age_min, age_max);

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM zz_seat s WHERE NOT EXISTS (SELECT 1 FROM zz_age a WHERE a.rank_name = s.rank_name)) THEN
    RAISE EXCEPTION 'для звания нет возрастного диапазона в zz_age';
  END IF;
END $$;

-- места без человека из архива
CREATE TEMP TABLE zz_need ON COMMIT DROP AS
SELECT s.*, row_number() OVER (ORDER BY s.subunit_code, s.seq, s.seat) AS k,
       random() AS r_nat, random() AS r_age, random() AS r_srv
FROM zz_seat s
WHERE NOT EXISTS (SELECT 1 FROM zz_match m WHERE (m.subunit_code, m.seq, m.seat) = (s.subunit_code, s.seq, s.seat));

CREATE TEMP TABLE zz_gen ON COMMIT DROP AS
SELECT n.*, z.nationality, z.ln, z.fn, z.pn, z.bp,
       -- срочники — 18–21 год, остальные — по диапазону звания
       (date '2026-11-01'
          - make_interval(years => CASE WHEN n.category = 'солдаты' AND n.r_srv < 0.6 THEN 18 ELSE a.age_min END)
          - make_interval(days => floor(n.r_age * ((CASE WHEN n.category = 'солдаты' AND n.r_srv < 0.6 THEN 4
                                                         ELSE a.age_max - a.age_min + 1 END) * 365))::int))::date AS birth_date,
       CASE WHEN n.category = 'солдаты' AND n.r_srv < 0.6 THEN 'срочная воинская служба' ELSE 'по контракту' END AS service_type
FROM zz_need n
JOIN zz_age a USING (rank_name)
JOIN zz_nat z ON n.r_nat * z.total > z.cum - z.n AND n.r_nat * z.total <= z.cum;

-- ---------------------------------------------------------------- люди
INSERT INTO district.person (person_id, personal_number, last_name, first_name, patronymic, sex, birth_date, nationality,
       birthplace, service_type, service_start, contract_end, education, marital_status, children, height_cm, weight_kg,
       blood_group, fitness_category, origin, legacy_person_id)
SELECT o.person_id, o.personal_number, o.last_name, o.first_name, o.patronymic, o.sex, o.birth_date, o.nationality,
       o.birthplace, o.service_type, o.service_start, o.contract_end, o.education, o.marital_status, coalesce(o.children, 0),
       o.height_cm, o.weight_kg, o.blood_group, o.fitness_category, 'reused', o.person_id
FROM zz_match m JOIN zz_old o ON o.person_id = m.legacy_id;

INSERT INTO district.person (person_id, personal_number, last_name, first_name, patronymic, sex, birth_date, nationality,
       birthplace, service_type, service_start, contract_end, education, marital_status, children, height_cm, weight_kg,
       blood_group, fitness_category, origin)
SELECT 100000 + g.k,
       'ЛН-' || lpad(((SELECT max(substring(personal_number FROM '\d+$')::int) FROM zz_old WHERE personal_number ~ '^ЛН-\d+$') + g.k)::text, 6, '0'),
       g.ln[1 + floor(random() * array_length(g.ln, 1))::int],
       g.fn[1 + floor(random() * array_length(g.fn, 1))::int],
       CASE WHEN g.pn IS NULL THEN NULL ELSE g.pn[1 + floor(random() * array_length(g.pn, 1))::int] END,
       'М', g.birth_date, g.nationality,
       CASE WHEN g.bp IS NULL THEN NULL ELSE g.bp[1 + floor(random() * array_length(g.bp, 1))::int] END,
       g.service_type,
       -- начало службы: срочники — за последние 11 мес., контрактники — с 19 лет и не позже чем год назад
       CASE WHEN g.service_type = 'срочная воинская служба'
            THEN date '2026-11-01' - floor(random() * 330)::int
            ELSE least(date '2025-11-01', (g.birth_date + interval '19 years')::date
                       + floor(random() * greatest(1, (date '2025-11-01' - (g.birth_date + interval '19 years')::date)))::int) END,
       NULL,
       CASE WHEN g.category = 'офицеры' THEN 'высшее военное'
            WHEN g.category = 'сержанты' THEN (ARRAY['техническое и профессиональное', 'техническое и профессиональное', 'общее среднее', 'высшее'])[1 + floor(random() * 4)::int]
            ELSE (ARRAY['общее среднее', 'общее среднее', 'общее среднее', 'техническое и профессиональное'])[1 + floor(random() * 4)::int] END,
       CASE WHEN date '2026-11-01' - g.birth_date > 26 * 365 AND random() < 0.65 THEN 'женат' ELSE 'холост' END,
       0,
       165 + floor(random() * 26)::int,
       0,
       (ARRAY['0(I) Rh+', '0(I) Rh+', '0(I) Rh+', 'A(II) Rh+', 'A(II) Rh+', 'A(II) Rh+', 'B(III) Rh+', 'B(III) Rh+',
              'AB(IV) Rh+', '0(I) Rh−', 'A(II) Rh−', 'B(III) Rh−'])[1 + floor(random() * 12)::int],
       CASE WHEN random() < 0.85 THEN 'А (годен)' ELSE 'Б (годен с незначительными ограничениями)' END,
       'generated'
FROM zz_gen g;

-- зависимые поля: вес от роста, дети у женатых, конец контракта (3 или 5 лет)
UPDATE district.person SET
  weight_kg = least(110, greatest(55, height_cm - 105 + floor(random() * 15)::int - 5)),
  children = CASE WHEN marital_status = 'женат' THEN floor(random() * 4)::int ELSE 0 END,
  contract_end = CASE WHEN service_type = 'по контракту'
                      THEN (service_start + make_interval(years => CASE WHEN random() < 0.5 THEN 3 ELSE 5 END)
                            * (1 + floor((date '2026-11-01' - service_start) / (365 * 4))::int))::date END
WHERE origin = 'generated';

-- ---------------------------------------------------------------- назначения на места
INSERT INTO district.person_post (subunit_code, seq, seat, person_id)
SELECT subunit_code, seq, seat, legacy_id FROM zz_match
UNION ALL
SELECT subunit_code, seq, seat, 100000 + k FROM zz_need;

-- ---------------------------------------------------------------- представление для Django (только чтение)
CREATE VIEW registry_api.subunit_people AS
SELECT pp.subunit_code, u.formation_code, f.district_code, u.subunit_name, u.level,
       st.seq, pp.seat, st.position_name, st.rank_name, r.category AS rank_category, r.sort_order AS rank_order,
       p.person_id, p.personal_number,
       p.last_name || ' ' || p.first_name || coalesce(' ' || p.patronymic, '') AS full_name,
       p.last_name, p.first_name, p.patronymic, p.sex, p.birth_date,
       date_part('year', age(date '2026-11-01', p.birth_date))::int AS age,
       p.nationality, p.birthplace, p.service_type, p.service_start, p.contract_end, p.education,
       p.marital_status, p.children, p.height_cm, p.weight_kg, p.blood_group, p.fitness_category,
       p.origin, p.confidence
FROM district.person_post pp
JOIN district.person p USING (person_id)
JOIN district.subunit_staff st ON st.subunit_code = pp.subunit_code AND st.seq = pp.seq
JOIN mil_core.rank r ON r.rank_name = st.rank_name
JOIN district.subunit u ON u.subunit_code = pp.subunit_code
JOIN district.formation f ON f.formation_code = u.formation_code;
COMMENT ON VIEW registry_api.subunit_people IS 'Вымышленный личный состав учебных округов (C): кто на какой должности';
GRANT SELECT ON registry_api.subunit_people TO registry_reader;

-- ---------------------------------------------------------------- проверки
DO $$ BEGIN
  IF (SELECT count(*) FROM district.person_post) <> (SELECT sum(qty) FROM district.subunit_staff) THEN
    RAISE EXCEPTION 'не на каждом штатном месте есть человек';
  END IF;
  IF (SELECT count(*) FROM district.person) <> (SELECT count(*) FROM district.person_post) THEN
    RAISE EXCEPTION 'есть люди без должности';
  END IF;
  IF EXISTS (SELECT 1 FROM registry_api.subunit_people WHERE age < 18 OR age > 60) THEN
    RAISE EXCEPTION 'возраст вне 18–60 лет';
  END IF;
  IF EXISTS (SELECT 1 FROM registry_api.subunit_people WHERE service_type = 'срочная воинская служба' AND age > 27) THEN
    RAISE EXCEPTION 'срочник старше 27 лет';
  END IF;
  IF EXISTS (SELECT 1 FROM registry_api.subunit_people WHERE rank_category <> 'солдаты' AND service_type = 'срочная воинская служба') THEN
    RAISE EXCEPTION 'срочник на должности сержанта или офицера';
  END IF;
  IF EXISTS (SELECT 1 FROM district.person WHERE last_name IS NULL OR first_name IS NULL) THEN
    RAISE EXCEPTION 'есть человек без фамилии или имени';
  END IF;
END $$;

COMMIT;

SELECT district_code, short_name, hq_city, formations, personnel_total, equipment_items, equipment_units, supply_pct, confidence
FROM registry_api.districts ORDER BY sort_order;
