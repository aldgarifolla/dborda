"""Only parameterized read-only queries to preapproved registry_api views.

Scope is always derived from the Django session user, never from submitted user IDs.
No raw SQL access is exposed to the browser or assistant.
"""
from django.db import connections
from .models import UnitGrant


def select(sql, args=()):
    with connections['military'].cursor() as cur:
        cur.execute(sql, args)
        columns = [col[0] for col in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def allowed_codes(user):
    if not user.is_authenticated:
        return set()
    roots = list(UnitGrant.objects.filter(user=user, is_active=True).values_list('root_code', flat=True))
    if not roots:
        return set()
    result = select('''
        WITH RECURSIVE scope(unit_code, path) AS (
          SELECT unit_code, ARRAY[unit_code]::text[]
          FROM registry_api.units WHERE unit_code = ANY(%s::text[])
          UNION ALL
          SELECT child.unit_code, scope.path || child.unit_code
          FROM registry_api.units child JOIN scope ON child.parent_code = scope.unit_code
          WHERE NOT child.unit_code = ANY(scope.path)
        )
        SELECT DISTINCT unit_code FROM scope
    ''', [roots])
    return {r['unit_code'] for r in result}


def get_unit(code, scope):
    if code not in scope:
        return None
    rows = select('''SELECT unit_code, parent_code, short_name, full_name,
                  level_name, country, model_personnel_own, data_status
                  FROM registry_api.units WHERE unit_code=%s''', [code])
    return rows[0] if rows else None


def list_units(scope, term='', limit=60):
    if not scope:
        return []
    pattern = '%' + term.strip()[:90] + '%'
    return select('''SELECT unit_code, parent_code, short_name, level_name, country
        FROM registry_api.units
        WHERE unit_code=ANY(%s::text[]) AND (short_name ILIKE %s OR full_name ILIKE %s OR unit_code ILIKE %s)
        ORDER BY length(unit_code), unit_code LIMIT %s''', [list(scope), pattern, pattern, pattern, limit])


def subtree(scope, code):
    if code not in scope:
        return []
    rows = select('''WITH RECURSIVE descendants(unit_code, path) AS (
            SELECT unit_code, ARRAY[unit_code]::text[] FROM registry_api.units WHERE unit_code=%s
            UNION ALL
            SELECT c.unit_code, d.path || c.unit_code FROM registry_api.units c
            JOIN descendants d ON c.parent_code=d.unit_code WHERE NOT c.unit_code=ANY(d.path)
        ) SELECT DISTINCT unit_code FROM descendants WHERE unit_code=ANY(%s::text[])''', [code, list(scope)])
    return [r['unit_code'] for r in rows]


def unit_children(scope, code):
    if not scope:
        return []
    return select('''SELECT unit_code, short_name, level_name FROM registry_api.units
              WHERE parent_code=%s AND unit_code=ANY(%s::text[])
              ORDER BY unit_code LIMIT 100''', [code, list(scope)])


def positions(codes, limit=100):
    if not codes:
        return []
    return select('''SELECT staff_id, unit_code, seq, position_name, rank_name, has_model_person_link
        FROM registry_api.staff_positions WHERE unit_code=ANY(%s::text[])
        ORDER BY unit_code, seq, staff_id LIMIT %s''', [list(codes), limit])


def holdings(codes, limit=100):
    if not codes:
        return []
    return select('''SELECT h.unit_code, h.item_sname, h.model_qty, h.derived_from, i.unit_measure
        FROM registry_api.holdings h LEFT JOIN registry_api.items i ON i.item_sname=h.item_sname
        WHERE h.unit_code=ANY(%s::text[]) ORDER BY h.unit_code, h.item_sname LIMIT %s''', [list(codes), limit])


def totals(codes):
    if not codes:
        return {'units': 0, 'positions': 0, 'linked_model_persons': 0, 'holdings_rows': 0}
    group = list(codes)
    r = select('''SELECT
        (SELECT count(*) FROM registry_api.units WHERE unit_code=ANY(%s::text[])) AS units,
        (SELECT count(*) FROM registry_api.staff_positions WHERE unit_code=ANY(%s::text[])) AS positions,
        (SELECT count(*) FROM registry_api.staff_positions WHERE unit_code=ANY(%s::text[])
            AND has_model_person_link) AS linked_model_persons,
        (SELECT count(*) FROM registry_api.holdings WHERE unit_code=ANY(%s::text[])) AS holdings_rows
    ''', [group, group, group, group])
    return r[0]


def item_catalog(term='', limit=100):
    pattern = '%' + term.strip()[:90] + '%'
    return select('''SELECT item_sname, item_name, category, unit_measure
        FROM registry_api.items WHERE item_sname ILIKE %s OR item_name ILIKE %s OR category ILIKE %s
        ORDER BY category, item_sname LIMIT %s''', [pattern, pattern, pattern, limit])


WORKBOOK_VIEWS = {
    'positions': ('registry_api.demo_excel_positions', 'source_row, formation, unit_code, unit_path, position_name, rank_name, model_slots'),
    'headcounts': ('registry_api.demo_excel_headcounts', 'source_row, formation, unit_code, unit_path, level_name, own_slots, aggregate_slots, data_status'),
    'assets': ('registry_api.demo_excel_assets', 'source_row, formation, unit_code, unit_path, item_name, model_qty, unit_measure, register_name'),
}


def workbook_rows(scope, kind, term='', limit=65):
    if not scope or kind not in WORKBOOK_VIEWS:
        return []
    # Identifiers are selected from a fixed whitelist, never from user input.
    view_name, fields = WORKBOOK_VIEWS[kind]
    pat = '%' + term.strip()[:90] + '%'
    return select(f'''SELECT {fields} FROM {view_name}
      WHERE unit_code=ANY(%s::text[]) AND (unit_path ILIKE %s OR unit_code ILIKE %s)
      ORDER BY source_row LIMIT %s''', [list(scope), pat, pat, limit])
