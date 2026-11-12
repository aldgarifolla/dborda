\set ON_ERROR_STOP on
-- Safe public summary only, no real names / personal profiles printed.
SELECT count(*) AS units FROM mil_core.unit;
SELECT count(*) AS staff_positions FROM mil_core.staff_position;
SELECT count(*) AS model_people FROM mil_core.person;
SELECT count(*) AS model_vehicles FROM mil_core.vehicle;
SELECT count(*) AS issued_items FROM mil_core.person_issue;
SELECT count(*) AS reference_rows FROM refdata.reference_entry;
SELECT sheet_name, count(*) AS imported_rows FROM refdata.workbook_row GROUP BY sheet_name ORDER BY sheet_name;
DO $$
BEGIN
 IF (SELECT count(*) FROM mil_core.unit) != 957 THEN RAISE EXCEPTION 'Unit count mismatch'; END IF;
 IF (SELECT count(*) FROM mil_core.staff_position) != 6993 THEN RAISE EXCEPTION 'Staff count mismatch'; END IF;
 IF (SELECT count(*) FROM mil_core.person) != 6993 THEN RAISE EXCEPTION 'Model people count mismatch'; END IF;
 IF (SELECT count(*) FROM mil_core.vehicle) != 1631 THEN RAISE EXCEPTION 'Vehicle count mismatch'; END IF;
 IF (SELECT count(*) FROM mil_core.person_issue) != 155859 THEN RAISE EXCEPTION 'Issued items mismatch'; END IF;
 IF (SELECT count(*) FROM refdata.reference_entry) != 54 THEN RAISE EXCEPTION 'Reference rows mismatch'; END IF;
 IF (SELECT count(*) FROM refdata.workbook_row) != 7982 THEN RAISE EXCEPTION 'Workbook demo row count mismatch'; END IF;
END $$;
-- Permission check: registry_reader must have access to safe views but no raw access.
SELECT has_table_privilege('registry_reader','registry_api.units','SELECT') AS can_read_safe_units,
       has_table_privilege('registry_reader','mil_core.person_profile','SELECT') AS can_read_person_profile,
       has_table_privilege('registry_reader','registry_api.demo_excel_positions','SELECT') AS can_read_demo_positions,
       has_function_privilege('registry_reader','mil_core.fn_request_fulfil(integer)','EXECUTE') AS can_fulfil_request;
