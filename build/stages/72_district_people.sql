-- Личный состав округов: вымышленные люди на штатных местах модели «всё по три».
-- Идемпотентно. Запускать ПОСЛЕ 70_districts.sql (тот пересоздаёт схему district и удаляет эти таблицы).
--
-- Откуда люди:
--   reused    — «свои» военнослужащие из исходного архива (mil_core.person + person_profile, синтетические по README
--               архива). Берутся по категории звания (солдаты / сержанты / офицеры), старшие по возрасту — на старшие
--               звания. Свои ФИО, дата рождения, национальность, анкета и личный номер сохраняются.
--   generated — недостающие места. ФИО собираются из фамилий, имён и отчеств людей архива той же национальности,
--               национальность — по долям архива, возраст, вид службы и образование — по званию (см. zz_age ниже).
-- Все данные ВЫМЫШЛЕННЫЕ (C). ИИН не создаётся: формат настоящего ИИН мог бы совпасть с номером реального человека.
-- Генератор детерминирован (setseed), повторный запуск даёт тех же людей.

BEGIN;

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
