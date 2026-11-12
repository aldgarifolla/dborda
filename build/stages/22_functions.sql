-- =====================================================================
--  Представления и функции для людей и ИИ-ассистента
-- =====================================================================

-- ------------------------------------------------------------------ читаемые представления
CREATE OR REPLACE VIEW mil_core.v_person AS
SELECT p.person_id, pp.personal_number, concat_ws(' ', p.last_name, p.first_name, p.patronymic) AS fio,
       s.rank_name, s.position_name, s.unit_code, u.short_name AS unit, u.full_name AS unit_full, u.country,
       pp.birth_date, date_part('year', age(current_date, pp.birth_date))::int AS age, pp.sex, pp.nationality, pp.birthplace,
       pp.height_cm, pp.weight_kg, round(pp.weight_kg / ((pp.height_cm / 100.0) ^ 2), 1) AS bmi,
       pp.clothing_size, pp.shoe_size, pp.head_size, pp.helmet_size, pp.glove_size,
       pp.blood_group, pp.fitness_category, pp.allergies, pp.last_med_exam,
       pp.service_type, pp.service_start, pp.contract_end, pp.education, pp.marital_status, pp.children,
       ca.vehicle_sname AS vehicle, v.tactical_no AS vehicle_tactical_no, ca.seat
FROM mil_core.person p
JOIN mil_core.person_profile pp USING (person_id)
JOIN mil_core.staff_position s USING (person_id)
JOIN mil_core.unit u USING (unit_code)
LEFT JOIN mil_core.crew_assignment ca USING (staff_id)
LEFT JOIN mil_core.vehicle v ON v.vehicle_id = ca.vehicle_id;

CREATE OR REPLACE VIEW mil_core.v_person_issue AS
SELECT i.person_id, concat_ws(' ', p.last_name, p.first_name, p.patronymic) AS fio, i.item_sname, it.item_name, it.category,
       i.qty, it.unit_measure, i.size, i.serial_no, i.issued_on, i.wear_until, k.kit_name
FROM mil_core.person_issue i JOIN mil_core.person p USING (person_id) JOIN mil_core.item it USING (item_sname)
LEFT JOIN mil_core.kit k USING (kit_code);

CREATE OR REPLACE VIEW mil_core.v_vehicle AS
SELECT v.vehicle_id, v.item_sname, i.item_name, v.unit_code, u.short_name AS unit, v.vehicle_no, v.tactical_no, v.factory_no,
       v.year_made, v.mileage_km, v.motor_hours, v.status,
       v.fuel_product, f.refill_l AS tank_capacity_l, v.fuel_level_l,
       CASE WHEN f.refill_l > 0 THEN round(100 * v.fuel_level_l / f.refill_l) END AS fuel_pct,
       f.refill_l - v.fuel_level_l AS to_full_l,
       v.cargo_product, v.cargo_level_l,
       (SELECT count(*) FROM mil_core.crew_assignment c WHERE c.vehicle_id = v.vehicle_id AND c.seat = 'экипаж') AS crew_on_board,
       (SELECT count(*) FROM mil_core.crew_assignment c WHERE c.vehicle_id = v.vehicle_id AND c.seat = 'десант') AS troops_on_board
FROM mil_core.vehicle v JOIN mil_core.item i USING (item_sname) JOIN mil_core.unit u USING (unit_code)
LEFT JOIN mil_core.v_item_fuel f USING (item_sname);

CREATE OR REPLACE VIEW mil_core.v_stock_balance AS
SELECT w.warehouse_id, w.warehouse_name, w.kind, m.item_sname, i.item_name, m.size, SUM(m.qty) AS balance, i.unit_measure,
       max(m.moved_at) AS last_movement
FROM mil_core.stock_movement m JOIN mil_core.warehouse w USING (warehouse_id) JOIN mil_core.item i USING (item_sname)
GROUP BY w.warehouse_id, w.warehouse_name, w.kind, m.item_sname, i.item_name, m.size, i.unit_measure;

CREATE OR REPLACE VIEW mil_core.v_stock_vs_norm AS
SELECT w.warehouse_id, w.warehouse_name, n.item_sname, i.item_name, n.size, n.norm_qty, COALESCE(b.balance, 0) AS balance,
       GREATEST(n.norm_qty - COALESCE(b.balance, 0), 0) AS deficit,
       round(100 * COALESCE(b.balance, 0) / NULLIF(n.norm_qty, 0)) AS provision_pct, i.unit_measure, n.basis
FROM mil_core.stock_norm n JOIN mil_core.warehouse w USING (warehouse_id) JOIN mil_core.item i USING (item_sname)
LEFT JOIN mil_core.v_stock_balance b ON b.warehouse_id = n.warehouse_id AND b.item_sname = n.item_sname AND b.size = n.size;

CREATE OR REPLACE VIEW mil_core.v_fuel_overview AS          -- где сколько топлива: баки, топливозаправщики, склады
SELECT product, place, SUM(litres) AS litres FROM (
  SELECT fuel_product AS product, 'в баках техники' AS place, fuel_level_l AS litres FROM mil_core.vehicle WHERE fuel_product IS NOT NULL
  UNION ALL SELECT cargo_product, 'на топливозаправщиках', cargo_level_l FROM mil_core.vehicle WHERE cargo_product IS NOT NULL
  UNION ALL SELECT item_sname, warehouse_name, balance FROM mil_core.v_stock_balance WHERE kind IN ('ГСМ','вышестоящий')
        AND item_sname IN (SELECT item_sname FROM mil_core.item WHERE category = 'Горючее и смазочные материалы')
) x GROUP BY product, place;

CREATE OR REPLACE VIEW mil_core.v_unit_fuel_state AS        -- по подразделению: ёмкость, налито, до полной, на ТЗ
SELECT t.root_code AS unit_code, v.fuel_product,
       count(*) AS vehicles, SUM(v.tank_capacity_l) AS capacity_l, SUM(v.fuel_level_l) AS in_tanks_l, SUM(v.to_full_l) AS to_full_l,
       SUM(CASE WHEN v.cargo_product = v.fuel_product THEN v.cargo_level_l ELSE 0 END) AS on_tankers_same_product_l
FROM mil_core.v_unit_tree t JOIN mil_core.v_vehicle v ON v.unit_code = t.unit_code
WHERE v.fuel_product IS NOT NULL GROUP BY t.root_code, v.fuel_product;

CREATE OR REPLACE VIEW mil_core.v_unit_property_total AS
SELECT t.root_code AS unit_code, p.item_sname, SUM(p.qty) AS qty
FROM mil_core.v_unit_tree t JOIN mil_core.unit_property p ON p.unit_code = t.unit_code GROUP BY 1, 2;

CREATE OR REPLACE VIEW mil_core.v_supply_request AS
SELECT r.request_id, r.created_at, r.requester_unit, u.short_name AS requester, w.warehouse_name AS to_warehouse, r.item_sname,
       i.item_name, r.size, r.qty, i.unit_measure, r.status, r.reason, r.created_by
FROM mil_core.supply_request r JOIN mil_core.unit u ON u.unit_code = r.requester_unit
JOIN mil_core.warehouse w ON w.warehouse_id = r.to_warehouse_id JOIN mil_core.item i USING (item_sname);

-- ------------------------------------------------------------------ функции
-- найти предмет по сокращению, полному названию или бытовому слову («бензин», «берцы», «сухпай»)
CREATE OR REPLACE FUNCTION mil_core.fn_resolve_item(p_text TEXT) RETURNS TEXT LANGUAGE sql STABLE AS $$
  SELECT item_sname FROM (
    SELECT item_sname, 1 AS pr FROM mil_core.item WHERE lower(item_sname) = lower(trim(p_text))
    UNION ALL SELECT item_sname, 2 FROM mil_core.item_alias WHERE alias = lower(trim(p_text))
    UNION ALL SELECT item_sname, 3 FROM mil_core.item WHERE item_sname ILIKE '%' || trim(p_text) || '%'
    UNION ALL SELECT item_sname, 4 FROM mil_core.item WHERE item_name ILIKE '%' || trim(p_text) || '%'
  ) x ORDER BY pr, length(item_sname) LIMIT 1
$$;

-- вид склада по категории предмета
CREATE OR REPLACE FUNCTION mil_core.fn_item_kind(p_item TEXT) RETURNS TEXT LANGUAGE sql STABLE AS $$
  SELECT CASE category
    WHEN 'Горючее и смазочные материалы' THEN 'ГСМ'
    WHEN 'Боеприпасы' THEN 'РАВ' WHEN 'Стрелковое оружие и гранатомёты' THEN 'РАВ'
    WHEN 'Продовольствие' THEN 'продовольственный'
    WHEN 'Средства индивидуальной защиты и медицинское имущество' THEN 'медицинский'
    ELSE 'вещевой' END
  FROM mil_core.item WHERE item_sname = p_item
$$;

-- склад, который обеспечивает подразделение этим видом имущества (ближайший по иерархии)
CREATE OR REPLACE FUNCTION mil_core.fn_warehouse_for(p_unit TEXT, p_kind TEXT) RETURNS INTEGER LANGUAGE sql STABLE AS $$
  SELECT warehouse_id FROM mil_core.warehouse
  WHERE p_unit LIKE serves_unit_code || '%' AND kind IN (p_kind, 'вышестоящий')
  ORDER BY length(serves_unit_code) DESC, (kind = 'вышестоящий') LIMIT 1
$$;

CREATE OR REPLACE FUNCTION mil_core.fn_balance(p_wh INTEGER, p_item TEXT, p_size TEXT DEFAULT '') RETURNS NUMERIC LANGUAGE sql STABLE AS $$
  SELECT COALESCE(SUM(qty), 0) FROM mil_core.stock_movement WHERE warehouse_id = p_wh AND item_sname = p_item AND size = COALESCE(p_size, '')
$$;

-- «Есть ли на складе 500 л бензина?» → JSON с ответом
CREATE OR REPLACE FUNCTION mil_core.fn_stock_check(p_item TEXT, p_qty NUMERIC, p_unit TEXT DEFAULT '20.0.6.0.0.2.', p_size TEXT DEFAULT '')
RETURNS JSONB LANGUAGE plpgsql STABLE AS $$
DECLARE v_item TEXT := mil_core.fn_resolve_item(p_item); v_wh INTEGER; v_bal NUMERIC; v_parent INTEGER; v_pbal NUMERIC;
BEGIN
  IF v_item IS NULL THEN RETURN jsonb_build_object('ok', false, 'message', format('Предмет «%s» не найден в каталоге', p_item)); END IF;
  v_wh := mil_core.fn_warehouse_for(p_unit, mil_core.fn_item_kind(v_item));
  v_bal := mil_core.fn_balance(v_wh, v_item, p_size);
  SELECT parent_warehouse_id INTO v_parent FROM mil_core.warehouse WHERE warehouse_id = v_wh;
  IF v_parent IS NOT NULL THEN v_pbal := mil_core.fn_balance(v_parent, v_item, p_size); END IF;
  RETURN jsonb_build_object(
    'ok', true, 'item', v_item, 'size', NULLIF(p_size, ''), 'requested', p_qty,
    'unit_measure', (SELECT unit_measure FROM mil_core.item WHERE item_sname = v_item),
    'warehouse', (SELECT warehouse_name FROM mil_core.warehouse WHERE warehouse_id = v_wh),
    'available', v_bal, 'enough', v_bal >= p_qty, 'deficit', GREATEST(p_qty - v_bal, 0),
    'parent_warehouse', (SELECT warehouse_name FROM mil_core.warehouse WHERE warehouse_id = v_parent), 'parent_available', v_pbal,
    'message', CASE WHEN v_bal >= p_qty THEN format('Да: на складе «%s» есть %s, запрошено %s', (SELECT warehouse_name FROM mil_core.warehouse WHERE warehouse_id = v_wh), v_bal, p_qty)
                    ELSE format('Нет: в наличии %s, не хватает %s. Можно создать заявку функцией fn_check_and_request', v_bal, p_qty - v_bal) END);
END $$;

-- создать заявку на склад, обеспечивающий подразделение
CREATE OR REPLACE FUNCTION mil_core.fn_request_create(p_unit TEXT, p_item TEXT, p_qty NUMERIC, p_reason TEXT DEFAULT NULL,
                                                      p_size TEXT DEFAULT '', p_created_by TEXT DEFAULT 'ассистент', p_to_wh INTEGER DEFAULT NULL)
RETURNS INTEGER LANGUAGE plpgsql AS $$
DECLARE v_item TEXT := mil_core.fn_resolve_item(p_item); v_id INTEGER;
BEGIN
  IF v_item IS NULL THEN RAISE EXCEPTION 'Предмет «%» не найден', p_item; END IF;
  INSERT INTO mil_core.supply_request (requester_unit, to_warehouse_id, item_sname, size, qty, reason, created_by)
  VALUES (p_unit, COALESCE(p_to_wh, mil_core.fn_warehouse_for(p_unit, mil_core.fn_item_kind(v_item))), v_item, COALESCE(p_size, ''), p_qty, p_reason, p_created_by)
  RETURNING request_id INTO v_id;
  RETURN v_id;
END $$;

-- проверить и, если не хватает, сразу оформить заявку на пополнение склада у вышестоящего
CREATE OR REPLACE FUNCTION mil_core.fn_check_and_request(p_item TEXT, p_qty NUMERIC, p_unit TEXT DEFAULT '20.0.6.0.0.2.',
                                                         p_reason TEXT DEFAULT NULL, p_size TEXT DEFAULT '')
RETURNS JSONB LANGUAGE plpgsql AS $$
DECLARE r JSONB := mil_core.fn_stock_check(p_item, p_qty, p_unit, p_size); v_wh INTEGER; v_parent INTEGER; v_owner TEXT; v_req INTEGER;
BEGIN
  IF NOT (r->>'ok')::boolean OR (r->>'enough')::boolean THEN RETURN r; END IF;
  SELECT warehouse_id, parent_warehouse_id, unit_code INTO v_wh, v_parent, v_owner
  FROM mil_core.warehouse WHERE warehouse_name = r->>'warehouse';
  v_req := mil_core.fn_request_create(v_owner, r->>'item', (r->>'deficit')::numeric,
             COALESCE(p_reason, format('нехватка на складе «%s» по запросу %s', r->>'warehouse', p_unit)), p_size, 'ассистент', COALESCE(v_parent, v_wh));
  RETURN r || jsonb_build_object('request_id', v_req, 'request_to', (SELECT warehouse_name FROM mil_core.warehouse WHERE warehouse_id = COALESCE(v_parent, v_wh)),
                                 'message', format('Не хватает %s. Создана заявка № %s на пополнение', r->>'deficit', v_req));
END $$;

-- выдать со склада подразделению (с проверкой остатка)
CREATE OR REPLACE FUNCTION mil_core.fn_issue(p_wh INTEGER, p_unit TEXT, p_item TEXT, p_qty NUMERIC, p_size TEXT DEFAULT '', p_doc TEXT DEFAULT NULL)
RETURNS BIGINT LANGUAGE plpgsql AS $$
DECLARE v_item TEXT := mil_core.fn_resolve_item(p_item); v_bal NUMERIC; v_id BIGINT;
BEGIN
  v_bal := mil_core.fn_balance(p_wh, v_item, p_size);
  IF v_bal < p_qty THEN RAISE EXCEPTION 'Недостаточно «%»: остаток %, запрошено %', v_item, v_bal, p_qty; END IF;
  INSERT INTO mil_core.stock_movement (warehouse_id, item_sname, size, qty, movement_type, counterparty, doc_no)
  VALUES (p_wh, v_item, COALESCE(p_size, ''), -p_qty, 'выдача', p_unit, p_doc) RETURNING movement_id INTO v_id;
  RETURN v_id;
END $$;

-- выполнить заявку: списать со склада-поставщика, при пополнении склада — оприходовать на складе того же вида у заявителя
CREATE OR REPLACE FUNCTION mil_core.fn_request_fulfil(p_request INTEGER) RETURNS TEXT LANGUAGE plpgsql AS $$
DECLARE r mil_core.supply_request; v_to INTEGER;
BEGIN
  SELECT * INTO r FROM mil_core.supply_request WHERE request_id = p_request FOR UPDATE;
  IF r.status = 'выполнена' THEN RETURN 'уже выполнена'; END IF;
  PERFORM mil_core.fn_issue(r.to_warehouse_id, r.requester_unit, r.item_sname, r.qty, r.size, 'заявка ' || p_request);
  SELECT warehouse_id INTO v_to FROM mil_core.warehouse WHERE unit_code = r.requester_unit AND kind = mil_core.fn_item_kind(r.item_sname);
  IF v_to IS NOT NULL THEN
    INSERT INTO mil_core.stock_movement (warehouse_id, item_sname, size, qty, movement_type, counterparty, doc_no, request_id)
    VALUES (v_to, r.item_sname, r.size, r.qty, 'приход', (SELECT warehouse_name FROM mil_core.warehouse WHERE warehouse_id = r.to_warehouse_id), 'заявка ' || p_request, p_request);
  END IF;
  UPDATE mil_core.supply_request SET status = 'выполнена' WHERE request_id = p_request;
  RETURN 'выполнена';
END $$;

-- найти человека по ФИО / фамилии / личному номеру
CREATE OR REPLACE FUNCTION mil_core.fn_find_person(p_text TEXT) RETURNS SETOF mil_core.v_person LANGUAGE sql STABLE AS $$
  SELECT * FROM mil_core.v_person WHERE fio ILIKE '%' || p_text || '%' OR personal_number = p_text ORDER BY fio LIMIT 50
$$;

-- полная карточка человека одним JSON
CREATE OR REPLACE FUNCTION mil_core.fn_person_card(p_person INTEGER) RETURNS JSONB LANGUAGE sql STABLE AS $$
  SELECT to_jsonb(v) || jsonb_build_object(
    'vaccinations', (SELECT jsonb_agg(jsonb_build_object('vaccine', vaccine, 'date', vaccinated_on) ORDER BY vaccinated_on) FROM mil_core.person_vaccination WHERE person_id = p_person),
    'issued', (SELECT jsonb_agg(jsonb_build_object('item', item_sname, 'qty', qty, 'size', size, 'serial', serial_no, 'issued_on', issued_on, 'wear_until', wear_until) ORDER BY category, item_sname)
               FROM mil_core.v_person_issue WHERE person_id = p_person))
  FROM mil_core.v_person v WHERE v.person_id = p_person
$$;

-- карточка машины: ТТХ, состояние, топливо, экипаж, возимый БК
CREATE OR REPLACE FUNCTION mil_core.fn_vehicle_card(p_vehicle INTEGER) RETURNS JSONB LANGUAGE sql STABLE AS $$
  SELECT to_jsonb(v) || jsonb_build_object(
    'crew', (SELECT jsonb_agg(jsonb_build_object('seat', c.seat, 'position', s.position_name, 'rank', s.rank_name,
                     'fio', concat_ws(' ', p.last_name, p.first_name, p.patronymic), 'person_id', p.person_id) ORDER BY c.seat, s.seq)
             FROM mil_core.crew_assignment c JOIN mil_core.staff_position s USING (staff_id) LEFT JOIN mil_core.person p USING (person_id)
             WHERE c.vehicle_id = p_vehicle),
    'ammo_load', (SELECT jsonb_agg(jsonb_build_object('ammo', ammo_sname, 'qty', qty, 'confidence', confidence))
                  FROM mil_core.vehicle_ammo_load WHERE vehicle_sname = v.item_sname),
    'specs', (SELECT jsonb_object_agg(param_name, COALESCE(value_num::text, value_text)) FROM (
                SELECT DISTINCT ON (param_name) param_name, value_num, value_text FROM mil_core.item_spec WHERE item_sname = v.item_sname ORDER BY param_name, confidence) s))
  FROM mil_core.v_vehicle v WHERE v.vehicle_id = p_vehicle
$$;

-- сводка по подразделению (любой уровень): люди, техника, топливо, имущество
CREATE OR REPLACE FUNCTION mil_core.fn_unit_card(p_unit TEXT) RETURNS JSONB LANGUAGE sql STABLE AS $$
  SELECT jsonb_build_object(
    'unit', (SELECT to_jsonb(u) FROM mil_core.unit u WHERE unit_code = p_unit),
    'personnel', (SELECT to_jsonb(x) FROM mil_core.v_unit_staff_by_category x WHERE unit_code = p_unit),
    'personnel_total_incl_estimates', (SELECT personnel FROM mil_core.v_unit_personnel WHERE unit_code = p_unit),
    'subunits', (SELECT jsonb_agg(jsonb_build_object('code', unit_code, 'name', short_name) ORDER BY sort_order) FROM mil_core.unit WHERE parent_code = p_unit),
    'vehicles', (SELECT jsonb_object_agg(item_sname, qty) FROM mil_core.v_unit_holding h WHERE unit_code = p_unit
                 AND item_sname IN (SELECT DISTINCT item_sname FROM mil_core.vehicle)),
    'vehicle_status', (SELECT jsonb_object_agg(status, n) FROM (SELECT v.status, count(*) n FROM mil_core.vehicle v WHERE v.unit_code LIKE p_unit || '%' GROUP BY 1) s),
    'fuel', (SELECT jsonb_agg(to_jsonb(f) - 'unit_code') FROM mil_core.v_unit_fuel_state f WHERE unit_code = p_unit),
    'group_property', (SELECT jsonb_object_agg(item_sname, qty) FROM mil_core.v_unit_property_total WHERE unit_code = p_unit),
    'need_by_norm_top', (SELECT jsonb_object_agg(item_sname, qty) FROM (SELECT item_sname, qty FROM mil_core.v_unit_need WHERE unit_code = p_unit ORDER BY qty DESC LIMIT 25) n),
    'open_requests', (SELECT jsonb_agg(to_jsonb(r)) FROM mil_core.v_supply_request r WHERE requester_unit = p_unit AND status <> 'выполнена'))
$$;

-- сколько топлива нужно подразделению на марш (условный расход × км), с учётом налитого
CREATE OR REPLACE FUNCTION mil_core.fn_march_fuel(p_unit TEXT, p_km NUMERIC)
RETURNS TABLE (fuel_product TEXT, vehicles BIGINT, need_l NUMERIC, in_tanks_l NUMERIC, to_add_l NUMERIC, no_rate_vehicles BIGINT) LANGUAGE sql STABLE AS $$
  SELECT v.fuel_product, count(*), round(SUM(COALESCE(r.value_num, 0) * p_km / 100)), SUM(v.fuel_level_l),
         GREATEST(round(SUM(COALESCE(r.value_num, 0) * p_km / 100) - SUM(v.fuel_level_l)), 0),
         count(*) FILTER (WHERE r.value_num IS NULL)
  FROM mil_core.vehicle v
  LEFT JOIN mil_core.item_spec r ON r.item_sname = v.item_sname AND r.param_name = 'Расход топлива на 100 км (условно)'
  WHERE v.unit_code LIKE p_unit || '%' AND v.fuel_product IS NOT NULL GROUP BY v.fuel_product
$$;

-- ------------------------------------------------------------------ комментарии (их читает ассистент через каталог)
COMMENT ON TABLE mil_core.person_profile IS 'Личная карточка (ВЫМЫШЛЕННЫЕ данные): дата рождения, национальность, рост, вес, размеры, группа крови, годность, вид службы';
COMMENT ON TABLE mil_core.person_vaccination IS 'Прививки военнослужащего';
COMMENT ON TABLE mil_core.person_issue IS 'Что выдано каждому: предмет, количество, размер, заводской номер (оружие, связь, приборы), срок носки';
COMMENT ON TABLE mil_core.vehicle IS 'Каждая машина отдельно: бортовой и заводской номер, пробег, состояние, топливо в баках, груз топливозаправщика';
COMMENT ON TABLE mil_core.unit_property IS 'Групповое имущество подразделения (палатки, аптечки взвода, комплекты санинструктора и т.п.), условные нормы';
COMMENT ON TABLE mil_core.warehouse IS 'Склады: вид, кто содержит, кого обеспечивает, вышестоящий склад для заявок';
COMMENT ON TABLE mil_core.stock_movement IS 'Движение по складам: остаток на начало, приход (+), выдача/списание (−). Остаток = сумма qty';
COMMENT ON TABLE mil_core.stock_norm IS 'Норма запаса склада (условная): заправки, боекомплекты, сутодачи, резерв по размерам';
COMMENT ON TABLE mil_core.supply_request IS 'Заявки на обеспечение: кто просит, у какого склада, что, сколько, статус';
COMMENT ON TABLE mil_core.item_alias IS 'Бытовые названия предметов для поиска: бензин → АИ-92, берцы → ботинки и т.д.';
COMMENT ON VIEW mil_core.v_person IS 'Плоская карточка человека: ФИО, звание, должность, подразделение, возраст, антропометрия, размеры, медицина, служба, машина и место';
COMMENT ON VIEW mil_core.v_stock_balance IS 'Текущие остатки на складах';
COMMENT ON VIEW mil_core.v_stock_vs_norm IS 'Остаток против нормы: дефицит и процент обеспеченности';
COMMENT ON VIEW mil_core.v_fuel_overview IS 'Сколько топлива какого вида: в баках, на топливозаправщиках, на складах';
COMMENT ON VIEW mil_core.v_unit_fuel_state IS 'По подразделению с подчинёнными: ёмкость баков, налито, сколько до полной, на ТЗ';
COMMENT ON FUNCTION mil_core.fn_stock_check(TEXT, NUMERIC, TEXT, TEXT) IS 'Есть ли на складе нужное количество. Пример: SELECT mil_core.fn_stock_check(''бензин'', 500)';
COMMENT ON FUNCTION mil_core.fn_check_and_request(TEXT, NUMERIC, TEXT, TEXT, TEXT) IS 'Проверить и при нехватке сразу создать заявку на вышестоящий склад';
COMMENT ON FUNCTION mil_core.fn_person_card(INTEGER) IS 'Полная карточка человека в JSON (данные, размеры, медицина, всё выданное с номерами)';
COMMENT ON FUNCTION mil_core.fn_vehicle_card(INTEGER) IS 'Полная карточка машины в JSON (ТТХ, топливо, экипаж поимённо, возимый БК)';
COMMENT ON FUNCTION mil_core.fn_unit_card(TEXT) IS 'Сводка по подразделению в JSON';
COMMENT ON FUNCTION mil_core.fn_march_fuel(TEXT, NUMERIC) IS 'Топливо на марш: fn_march_fuel(код, км)';
