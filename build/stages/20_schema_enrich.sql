-- =====================================================================
--  Расширение mil_core: личные карточки, выдача имущества, техника поштучно,
--  склады и движение, нормы запасов, заявки, функции для ИИ-ассистента.
--  Все персональные данные ВЫМЫШЛЕННЫЕ. Нормы запасов и расхода — условные (контрольный пример).
-- =====================================================================

-- ------------------------------------------------------------------ люди
CREATE TABLE mil_core.person_profile (
    person_id        INTEGER PRIMARY KEY REFERENCES mil_core.person ON DELETE CASCADE,
    personal_number  TEXT UNIQUE,                 -- условный личный номер
    birth_date       DATE NOT NULL,
    sex              CHAR(1) NOT NULL CHECK (sex IN ('М','Ж')),
    nationality      TEXT NOT NULL,
    birthplace       TEXT,
    height_cm        SMALLINT NOT NULL CHECK (height_cm BETWEEN 140 AND 215),
    weight_kg        SMALLINT NOT NULL CHECK (weight_kg BETWEEN 40 AND 150),
    chest_cm         SMALLINT NOT NULL,
    head_cm          SMALLINT NOT NULL,
    clothing_size    TEXT NOT NULL,               -- размер-рост, напр. 48-4 (РФ) или M-Regular (США)
    shoe_size        TEXT NOT NULL,
    head_size        TEXT NOT NULL,
    helmet_size      TEXT NOT NULL,
    glove_size       TEXT NOT NULL,
    blood_group      TEXT NOT NULL,
    fitness_category TEXT NOT NULL,               -- категория годности
    service_type     TEXT NOT NULL CHECK (service_type IN ('по призыву','по контракту','офицер кадра')),
    service_start    DATE NOT NULL,
    contract_end     DATE,
    education        TEXT,
    marital_status   TEXT,
    children         SMALLINT DEFAULT 0,
    allergies        TEXT DEFAULT 'нет',
    last_med_exam    DATE
);
CREATE TABLE mil_core.person_vaccination (
    person_id INTEGER REFERENCES mil_core.person ON DELETE CASCADE, vaccine TEXT, vaccinated_on DATE,
    PRIMARY KEY (person_id, vaccine));

-- выданное военнослужащему имущество (вещевой аттестат + закреплённое оружие)
CREATE TABLE mil_core.person_issue (
    issue_id    SERIAL PRIMARY KEY,
    person_id   INTEGER NOT NULL REFERENCES mil_core.person ON DELETE CASCADE,
    item_sname  TEXT NOT NULL REFERENCES mil_core.item,
    qty         INTEGER NOT NULL CHECK (qty > 0),
    size        TEXT,
    serial_no   TEXT UNIQUE,                     -- заводской номер (оружие, радиостанции, приборы)
    issued_on   DATE NOT NULL,
    wear_until  DATE,                            -- до какого срока носки
    kit_code    TEXT REFERENCES mil_core.kit
);
CREATE INDEX ix_issue_person ON mil_core.person_issue(person_id);
CREATE INDEX ix_issue_item ON mil_core.person_issue(item_sname);

-- ------------------------------------------------------------------ техника поштучно
CREATE TABLE mil_core.vehicle (
    vehicle_id     SERIAL PRIMARY KEY,
    item_sname     TEXT NOT NULL REFERENCES mil_core.item,
    unit_code      TEXT NOT NULL REFERENCES mil_core.unit,
    vehicle_no     INTEGER NOT NULL,             -- номер машины внутри подразделения (как в посадке)
    tactical_no    TEXT,                         -- бортовой номер
    factory_no     TEXT UNIQUE,
    year_made      SMALLINT,
    mileage_km     INTEGER,
    motor_hours    INTEGER,
    status         TEXT NOT NULL CHECK (status IN ('исправна','требует ТО','требует ремонта','в ремонте')),
    fuel_product   TEXT REFERENCES mil_core.item,       -- чем заправляется
    fuel_level_l   NUMERIC(8,1),                         -- сейчас в баках
    cargo_product  TEXT REFERENCES mil_core.item,       -- для топливозаправщиков: что везёт
    cargo_level_l  NUMERIC(8,1),
    UNIQUE (unit_code, item_sname, vehicle_no)
);
CREATE INDEX ix_vehicle_unit ON mil_core.vehicle(unit_code);
ALTER TABLE mil_core.crew_assignment ADD COLUMN vehicle_id INTEGER REFERENCES mil_core.vehicle;

-- групповое имущество подразделения (палатки, медицинские комплекты взвода и т.п.)
CREATE TABLE mil_core.unit_property (
    unit_code  TEXT REFERENCES mil_core.unit, item_sname TEXT REFERENCES mil_core.item,
    qty INTEGER NOT NULL CHECK (qty >= 0), basis TEXT, PRIMARY KEY (unit_code, item_sname));

-- ------------------------------------------------------------------ склады
CREATE TABLE mil_core.warehouse (
    warehouse_id        SERIAL PRIMARY KEY,
    warehouse_name      TEXT NOT NULL UNIQUE,
    kind                TEXT NOT NULL CHECK (kind IN ('ГСМ','РАВ','вещевой','продовольственный','медицинский','вышестоящий')),
    unit_code           TEXT NOT NULL REFERENCES mil_core.unit,      -- кто содержит склад
    serves_unit_code    TEXT NOT NULL REFERENCES mil_core.unit,      -- кого обеспечивает (вся ветка)
    parent_warehouse_id INTEGER REFERENCES mil_core.warehouse,       -- куда идёт заявка при нехватке
    capacity_note       TEXT
);
CREATE TABLE mil_core.stock_movement (
    movement_id    BIGSERIAL PRIMARY KEY,
    warehouse_id   INTEGER NOT NULL REFERENCES mil_core.warehouse,
    item_sname     TEXT NOT NULL REFERENCES mil_core.item,
    size           TEXT NOT NULL DEFAULT '',
    qty            NUMERIC NOT NULL CHECK (qty <> 0),               -- + приход, − расход
    movement_type  TEXT NOT NULL CHECK (movement_type IN ('остаток на начало','приход','выдача','списание','перемещение')),
    moved_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    counterparty   TEXT,                                            -- подразделение / поставщик
    doc_no         TEXT,
    request_id     INTEGER
);
CREATE INDEX ix_mv_wh_item ON mil_core.stock_movement(warehouse_id, item_sname, size);

CREATE TABLE mil_core.stock_norm (                 -- норма запаса склада (условная)
    warehouse_id INTEGER REFERENCES mil_core.warehouse, item_sname TEXT REFERENCES mil_core.item, size TEXT NOT NULL DEFAULT '',
    norm_qty NUMERIC NOT NULL, basis TEXT NOT NULL, PRIMARY KEY (warehouse_id, item_sname, size));

CREATE TABLE mil_core.supply_request (
    request_id      SERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    requester_unit  TEXT NOT NULL REFERENCES mil_core.unit,
    to_warehouse_id INTEGER NOT NULL REFERENCES mil_core.warehouse,
    item_sname      TEXT NOT NULL REFERENCES mil_core.item,
    size            TEXT NOT NULL DEFAULT '',
    qty             NUMERIC NOT NULL CHECK (qty > 0),
    status          TEXT NOT NULL DEFAULT 'создана' CHECK (status IN ('создана','согласована','выполнена','отклонена')),
    reason          TEXT,
    created_by      TEXT NOT NULL DEFAULT 'пользователь'
);
ALTER TABLE mil_core.stock_movement ADD FOREIGN KEY (request_id) REFERENCES mil_core.supply_request;
