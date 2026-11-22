-- СПРАВОЧНИК. Этап вида reference. Региональные командования (округа) ВС РК по открытым источникам.
-- Учебная база. Сюда внесены только сведения уровня энциклопедии и опубликованных указов:
-- название, город штаба, год образования, зона ответственности по областям.
-- Численность, состав, дислокация частей и фамилии командующих НЕ вносятся: в открытых нормативных
-- источниках их нет, а выдумывать их здесь нельзя.
--
-- Шкала достоверности (как в mil_core):
--   A — дословно из опубликованного нормативного акта;
--   B — из СМИ или выведено из акта (например, область выделена позже из области, указанной в акте);
--   C — условное значение.
-- ВАЖНО: последний опубликованный акт о зонах ответственности — Указ № 354 от 12.07.2012. Он утратил силу
-- Указом № 676-ДСП от 27.04.2018, текст которого не опубликован. Поэтому зоны даны «по состоянию
-- на 2012–2018 гг.» и как действующие не подтверждены. verified_for_operational_use = false везде.
-- Повторный запуск обновляет строки на месте (таблицы не пересоздаются: на них ссылается этап 70).
\set ON_ERROR_STOP on
BEGIN;

CREATE TABLE IF NOT EXISTS refdata.kz_rc_source (
    source_code TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    publisher   TEXT NOT NULL,
    url         TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('нормативный акт', 'СМИ', 'энциклопедия')),
    published   TEXT,
    accessed_on DATE NOT NULL,
    note        TEXT
);
COMMENT ON TABLE refdata.kz_rc_source IS 'Источники справочника региональных командований ВС РК (открытые)';

CREATE TABLE IF NOT EXISTS refdata.kz_regional_command (
    rc_code      TEXT PRIMARY KEY,
    short_name   TEXT NOT NULL UNIQUE,
    full_name    TEXT NOT NULL,
    hq_city      TEXT NOT NULL,
    hq_confidence CHAR(1) NOT NULL CHECK (hq_confidence IN ('A','B','C')),
    hq_source    TEXT NOT NULL REFERENCES refdata.kz_rc_source,
    formed_on    DATE NOT NULL,
    formed_basis TEXT NOT NULL,
    formed_source TEXT NOT NULL REFERENCES refdata.kz_rc_source,
    predecessor  TEXT,
    predecessor_confidence CHAR(1) CHECK (predecessor_confidence IN ('A','B','C')),
    sort_order   INT NOT NULL,
    verified_for_operational_use BOOLEAN NOT NULL DEFAULT false CHECK (NOT verified_for_operational_use)
);
COMMENT ON TABLE refdata.kz_regional_command IS
  'Региональные командования ВС РК (уровень округа). Открытые сведения, учебная база, для эксплуатации не проверено';

CREATE TABLE IF NOT EXISTS refdata.kz_rc_region (
    rc_code     TEXT NOT NULL REFERENCES refdata.kz_regional_command,
    region_name TEXT NOT NULL PRIMARY KEY,
    region_kind TEXT NOT NULL CHECK (region_kind IN ('область', 'город республиканского значения')),
    confidence  CHAR(1) NOT NULL CHECK (confidence IN ('A','B','C')),
    source_code TEXT NOT NULL REFERENCES refdata.kz_rc_source,
    basis       TEXT NOT NULL,
    as_of       TEXT NOT NULL,
    verified_for_operational_use BOOLEAN NOT NULL DEFAULT false CHECK (NOT verified_for_operational_use)
);
COMMENT ON TABLE refdata.kz_rc_region IS
  'Зона ответственности региональных командований по областям. По Указу № 354 (2012, утратил силу в 2018) и выводу для областей, образованных позже';

INSERT INTO refdata.kz_rc_source VALUES
 ('UKAZ-1085-2003', 'Указ Президента РК от 07.05.2003 № 1085 «О мерах по дальнейшему совершенствованию структуры Вооруженных Сил Республики Казахстан»',
  'Президент РК (текст: zakon.uchet.kz)', 'https://zakon.uchet.kz/rus/docs/U030001085_', 'нормативный акт', '2003-05-07', '2026-11-12',
  'утратил силу Указом от 12.07.2012 № 354'),
 ('UKAZ-354-2012', 'Указ Президента РК от 12.07.2012 № 354 (зоны ответственности региональных командований)',
  'Президент РК (текст: zakon.uchet.kz)', 'https://zakon.uchet.kz/rus/docs/U1200000354', 'нормативный акт', '2012-07-12', '2026-11-12',
  'утратил силу Указом от 27.04.2018 № 676-ДСП (текст не опубликован)'),
 ('KAPITAL-2014', '«У Казахстана самая мощная армия в Центральной Азии»', 'Kapital.kz',
  'https://kapital.kz/gosudarstvo/29796/u-kazahstana-samaya-mocshnaya-armiya-v-centralnoj-azii.html', 'СМИ', '2014-05-11', '2026-11-12',
  'штабы: Караганда, Семипалатинск, Атырау, Тараз'),
 ('WIKI-VS-RK', 'Вооружённые силы Республики Казахстан', 'Википедия',
  'https://ru.wikipedia.org/wiki/Вооружённые_силы_Республики_Казахстан', 'энциклопедия', NULL, '2026-11-12',
  'военные округа созданы указом от 06.07.2000, в мае 2003 г. преобразованы в региональные командования')
ON CONFLICT (source_code) DO UPDATE SET title = EXCLUDED.title, publisher = EXCLUDED.publisher, url = EXCLUDED.url,
  source_type = EXCLUDED.source_type, published = EXCLUDED.published, accessed_on = EXCLUDED.accessed_on, note = EXCLUDED.note;

INSERT INTO refdata.kz_regional_command VALUES
 ('РгК-АСТ', 'РгК «Астана»', 'региональное командование «Астана»', 'Караганда', 'B', 'KAPITAL-2014',
  '2003-05-07', 'Указ № 1085 определил зоны ответственности четырёх региональных командований', 'UKAZ-1085-2003',
  'Центральный военный округ (2000–2003)', 'B', 1, false),
 ('РгК-ВОС', 'РгК «Восток»', 'региональное командование «Восток»', 'Семей (до 2007 г. Семипалатинск)', 'B', 'KAPITAL-2014',
  '2003-05-07', 'Указ № 1085 определил зоны ответственности четырёх региональных командований', 'UKAZ-1085-2003',
  'Восточный военный округ (2000–2003)', 'B', 2, false),
 ('РгК-ЗАП', 'РгК «Запад»', 'региональное командование «Запад»', 'Атырау', 'B', 'KAPITAL-2014',
  '2003-05-07', 'Указ № 1085 определил зоны ответственности четырёх региональных командований', 'UKAZ-1085-2003',
  'Западный военный округ (2000–2003)', 'B', 3, false),
 ('РгК-ЮГ', 'РгК «Юг»', 'региональное командование «Юг»', 'Тараз', 'B', 'KAPITAL-2014',
  '2003-05-07', 'Указ № 1085 определил зоны ответственности четырёх региональных командований', 'UKAZ-1085-2003',
  'Южный военный округ (2000–2003)', 'B', 4, false)
ON CONFLICT (rc_code) DO UPDATE SET short_name = EXCLUDED.short_name, full_name = EXCLUDED.full_name, hq_city = EXCLUDED.hq_city,
  hq_confidence = EXCLUDED.hq_confidence, hq_source = EXCLUDED.hq_source, formed_on = EXCLUDED.formed_on,
  formed_basis = EXCLUDED.formed_basis, formed_source = EXCLUDED.formed_source, predecessor = EXCLUDED.predecessor,
  predecessor_confidence = EXCLUDED.predecessor_confidence, sort_order = EXCLUDED.sort_order;

INSERT INTO refdata.kz_rc_region (rc_code, region_name, region_kind, confidence, source_code, basis, as_of) VALUES
 ('РгК-АСТ', 'г. Астана',                     'город республиканского значения', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-АСТ', 'Акмолинская область',           'область', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-АСТ', 'Карагандинская область',        'область', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-АСТ', 'Костанайская область',          'область', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-АСТ', 'Северо-Казахстанская область',  'область', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-АСТ', 'область Улытау',                'область', 'B', 'UKAZ-354-2012',
  'вывод: область выделена в 2022 г. из Карагандинской; действующее распределение не опубликовано', 'вывод на 2022'),
 ('РгК-ВОС', 'Восточно-Казахстанская область', 'область', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-ВОС', 'Павлодарская область',          'область', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-ВОС', 'область Абай',                  'область', 'B', 'UKAZ-354-2012',
  'вывод: область выделена в 2022 г. из Восточно-Казахстанской; действующее распределение не опубликовано', 'вывод на 2022'),
 ('РгК-ЗАП', 'Актюбинская область',           'область', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-ЗАП', 'Атырауская область',            'область', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-ЗАП', 'Западно-Казахстанская область', 'область', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-ЗАП', 'Мангистауская область',         'область', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-ЮГ',  'г. Алматы',                     'город республиканского значения', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-ЮГ',  'Алматинская область',           'область', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-ЮГ',  'Жамбылская область',            'область', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-ЮГ',  'Кызылординская область',        'область', 'A', 'UKAZ-354-2012', 'указ № 354, п. 2', '2012–2018'),
 ('РгК-ЮГ',  'Туркестанская область',         'область', 'B', 'UKAZ-354-2012',
  'вывод: в указе — Южно-Казахстанская область, переименована в Туркестанскую в 2018 г.', 'вывод на 2018'),
 ('РгК-ЮГ',  'г. Шымкент',                    'город республиканского значения', 'B', 'UKAZ-354-2012',
  'вывод: город выделен из Южно-Казахстанской области в 2018 г.', 'вывод на 2018'),
 ('РгК-ЮГ',  'область Жетісу',                'область', 'B', 'UKAZ-354-2012',
  'вывод: область выделена в 2022 г. из Алматинской; действующее распределение не опубликовано', 'вывод на 2022')
ON CONFLICT (region_name) DO UPDATE SET rc_code = EXCLUDED.rc_code, region_kind = EXCLUDED.region_kind,
  confidence = EXCLUDED.confidence, source_code = EXCLUDED.source_code, basis = EXCLUDED.basis, as_of = EXCLUDED.as_of;

DO $$ BEGIN
  IF (SELECT count(*) FROM refdata.kz_rc_region) <> 20 THEN
    RAISE EXCEPTION 'ожидалось 20 административных единиц (17 областей и 3 города республиканского значения)';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'registry_reader') THEN
    GRANT SELECT ON refdata.kz_rc_source, refdata.kz_regional_command, refdata.kz_rc_region TO registry_reader;
  END IF;
END $$;

COMMIT;
