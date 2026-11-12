-- РУЧНЫЕ ДЕЙСТВИЯ, попавшие в базовый дамп init/10_full.sql. Этап вида manual.
-- В скриптах сборки этих записей нет. Они появились 29.10.2026 в 12:52:50 (+05) в одну секунду,
-- после kz_localize (в движении уже новое название склада). По содержанию совпадают с двумя
-- демонстрационными запросами из queries_assistant.sql сборки 29 октября:
--   строка 5:  fn_check_and_request('бензин', 500, '20.0.6.0.0.2.2.', 'заправка техники 1 мсб')
--              -> заявка № 4 на недостающие 120 л АИ-92 (на складе 380 л из 500);
--   строка 59: fn_request_fulfil(первая заявка в статусе «создана»)
--              -> заявка № 2 выполнена, движения 1136 (выдача) и 1137 (приход).
-- Это вероятное объяснение, прямого журнала запуска нет. Значения ниже перенесены из дампа дословно,
-- включая время и номера; номера 3, 5 и 1138, 1139 израсходованы последовательностями без строк.
\set ON_ERROR_STOP on
UPDATE mil_core.supply_request SET status = 'выполнена' WHERE request_id = 2 AND status = 'создана';
INSERT INTO mil_core.supply_request (request_id, created_at, requester_unit, to_warehouse_id, item_sname, size, qty, status, reason, created_by)
VALUES (4, '2026-10-29 12:52:50.024249+05', '20.0.6.0.0.2.13.2.', 2, 'АИ-92', '', 120.0, 'создана', 'заправка техники 1 мсб', 'ассистент')
ON CONFLICT (request_id) DO NOTHING;
INSERT INTO mil_core.stock_movement (movement_id, warehouse_id, item_sname, size, qty, movement_type, moved_at, counterparty, doc_no, request_id)
VALUES (1136, 2, 'Ботинки с высокими берцами', '46', -12, 'выдача', '2026-10-29 12:52:50.104605+05', '20.0.6.0.0.2.13.2.', 'заявка 2', NULL),
       (1137, 5, 'Ботинки с высокими берцами', '46', 12, 'приход', '2026-10-29 12:52:50.104605+05', 'Склад объединения (вышестоящий, условно)', 'заявка 2', 2)
ON CONFLICT (movement_id) DO NOTHING;
SELECT setval('mil_core.supply_request_request_id_seq', 5, true);
SELECT setval('mil_core.stock_movement_movement_id_seq', 1139, true);
