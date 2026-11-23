"""Only parameterized read-only queries to preapproved registry_api views.

Scope is always derived from the Django session user, never from submitted user IDs.
No raw SQL access is exposed to the browser or assistant.

Уровень данных — округа: региональные командования ВС РК (registry_api.district*); числа учебные. Область доступа
пользователя — множество кодов округов из UnitGrant.root_code.
"""
from decimal import Decimal

from django.db import connections

from .models import UnitGrant

PAGE_SIZE = 50
METRICS = {
    'personnel': ('personnel_total', 'Численность, чел.'),
    'equipment': ('equipment_units', 'Техника и вооружение, ед.'),
    'supply': ('supply_pct', 'Обеспеченность запасами, %'),
    'formations': ('formations', 'Соединений'),
}


def _plain(value):
    """Decimal -> int/float, чтобы строки можно было хранить в сессии и отдавать помощнику."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def select(sql, args=()):
    with connections['military'].cursor() as cur:
        cur.execute(sql, args)
        columns = [col[0] for col in cur.description]
        return [dict(zip(columns, map(_plain, row))) for row in cur.fetchall()]


def like(term):
    """Шаблон ILIKE по подстроке; %, _ и \\ во вводе пользователя экранируются."""
    cleaned = term.strip()[:90].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return '%' + cleaned + '%'


def page_bounds(page):
    try:
        page = max(1, min(int(page), 10_000))
    except (TypeError, ValueError):
        page = 1
    return page, (page - 1) * PAGE_SIZE


# ---------------------------------------------------------------- область доступа
def allowed_codes(user):
    """Коды округов, на которые пользователю выданы активные права и которые есть в базе."""
    if not user.is_authenticated:
        return set()
    granted = list(UnitGrant.objects.filter(user=user, is_active=True).values_list('root_code', flat=True))
    if not granted:
        return set()
    rows = select('SELECT district_code FROM registry_api.districts WHERE district_code = ANY(%s::text[])', [granted])
    return {r['district_code'] for r in rows}


# ---------------------------------------------------------------- округа
DISTRICT_FIELDS = '''district_code, short_name, full_name, hq_city, side, zone_note, origin, confidence,
                     formations, personnel_total, equipment_items, equipment_units, supply_pct'''


def list_districts(scope):
    if not scope:
        return []
    return select(f'''SELECT {DISTRICT_FIELDS} FROM registry_api.districts
                      WHERE district_code = ANY(%s::text[]) ORDER BY sort_order''', [list(scope)])


def get_district(code, scope):
    if code not in scope:
        return None
    rows = select(f'SELECT {DISTRICT_FIELDS} FROM registry_api.districts WHERE district_code = %s', [code])
    return rows[0] if rows else None


def totals(scope):
    if not scope:
        return {'districts': 0, 'formations': 0, 'personnel': 0, 'equipment_units': 0}
    return select('''SELECT count(*) AS districts, coalesce(sum(formations), 0) AS formations,
                            coalesce(sum(personnel_total), 0) AS personnel,
                            coalesce(sum(equipment_units), 0) AS equipment_units
                     FROM registry_api.districts WHERE district_code = ANY(%s::text[])''', [list(scope)])[0]


def regions(code, scope):
    """Области и города в зоне ответственности округа, с источником и достоверностью."""
    if code not in scope:
        return []
    return select('''SELECT region_name, region_kind, confidence, basis, as_of, source_title, source_url
                     FROM registry_api.district_regions WHERE district_code = %s
                     ORDER BY region_kind DESC, region_name''', [code])


def formations(code, scope):
    if code not in scope:
        return []
    return select('''SELECT formation_code, formation_name, formation_type, origin,
                            battalions, companies, platoons, squads, personnel, equipment_units
                     FROM registry_api.district_formations WHERE district_code = %s ORDER BY formation_code''', [code])


def get_formation(formation_code, scope):
    """Соединение, только если его округ входит в область доступа."""
    if not scope:
        return None
    rows = select('''SELECT f.formation_code, f.district_code, d.short_name AS district_name, f.formation_name,
                         f.formation_type, f.origin, f.battalions, f.companies, f.platoons, f.squads,
                         f.personnel, f.officers, f.sergeants, f.soldiers, f.equipment_units
                  FROM registry_api.district_formations f JOIN registry_api.districts d USING (district_code)
                  WHERE f.formation_code = %s AND f.district_code = ANY(%s::text[])''', [formation_code, list(scope)])
    return rows[0] if rows else None


def subunits(formation_code, scope):
    """Все подразделения соединения (батальон -> рота -> взвод -> отделение) в порядке штата."""
    if not scope:
        return []
    return select('''SELECT subunit_code, parent_code, level, level_rank, subunit_name, confidence, norm_kind,
                            own_personnel, personnel, officers, sergeants, soldiers, equipment_units
                     FROM registry_api.district_subunits
                     WHERE formation_code = %s AND district_code = ANY(%s::text[])
                     ORDER BY sort_key''', [formation_code, list(scope)])


CATEGORY_ORDER = "array_position(ARRAY['офицеры', 'сержанты', 'солдаты'], category)"


def like_prefix(code):
    """Подчинённые: код начинается с кода старшего и точки. Спецсимволы LIKE экранируются."""
    return code.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '.%'


def unit_staff(code, scope, own_only=False):
    """Должности подразделения или соединения (code). own_only — только собственные (управление),
    иначе — сгруппированные по всем подчинённым."""
    if not scope:
        return []
    if own_only:
        return select('''SELECT position_name, rank_name, category, qty, source_code, source_title, source_url, confidence
                         FROM registry_api.subunit_staff WHERE subunit_code = %s AND district_code = ANY(%s::text[])
                         ORDER BY seq''', [code, list(scope)])
    return select(f'''SELECT position_name, rank_name, category, sum(qty) AS qty, source_code, source_title, source_url, confidence
                      FROM registry_api.subunit_staff
                      WHERE (subunit_code = %s OR subunit_code LIKE %s) AND district_code = ANY(%s::text[])
                      GROUP BY position_name, rank_name, category, source_code, source_title, source_url, confidence
                      ORDER BY {CATEGORY_ORDER}, sum(qty) DESC, position_name''', [code, like_prefix(code), list(scope)])


def search_words(term, limit=4):
    """Слова запроса по основам: «командир батальона» -> «командир», «батальо» — найдёт
    «Командир механизированного батальона». Короткие слова (до 3 букв) пропускаются."""
    words = [w for w in str(term or '').replace('ё', 'е').split() if len(w) > 3 or w.upper().startswith('ЛН')]
    return [w if w.upper().startswith('ЛН') else w[:max(4, int(len(w) * 0.75))] for w in words][:limit]


PEOPLE_COLUMNS = ('subunit_code, subunit_name, formation_code, level, seq, seat, position_name, rank_name, rank_category, '
                  'personal_number, full_name, age, service_type, nationality')
PEOPLE_CATEGORIES = ('офицеры', 'сержанты', 'солдаты')
PEOPLE_SERVICES = ('срочная воинская служба', 'по контракту')


def unit_people(code, scope, page=1, term='', category='', service='', district=''):
    """Вымышленный личный состав подразделения вместе с подчинёнными (или всего округа, если задан district):
    (строки страницы, всего). term — поиск по ФИО, должности или личному номеру; category — офицеры/сержанты/солдаты;
    service — срочная воинская служба / по контракту."""
    if not scope:
        return [], 0
    page, offset = page_bounds(page)
    if district:
        where, args = 'district_code = %s AND district_code = ANY(%s::text[])', [district, list(scope)]
    else:
        where = '(subunit_code = %s OR subunit_code LIKE %s) AND district_code = ANY(%s::text[])'
        args = [code, like_prefix(code), list(scope)]
    for word in search_words(term):             # каждое слово (по основе) — в ФИО, должности или личном номере
        where += ' AND (full_name ILIKE %s OR position_name ILIKE %s OR personal_number ILIKE %s)'
        args += [like(word)] * 3
    if category in PEOPLE_CATEGORIES:
        where += ' AND rank_category = %s'
        args.append(category)
    if service in PEOPLE_SERVICES:
        where += ' AND service_type = %s'
        args.append(service)
    total = select(f'SELECT count(*) AS n FROM registry_api.subunit_people WHERE {where}', args)[0]['n']
    rows = select(f'SELECT {PEOPLE_COLUMNS} FROM registry_api.subunit_people WHERE {where} '
                  'ORDER BY subunit_code, seq, seat LIMIT %s OFFSET %s', args + [PAGE_SIZE, offset])
    return rows, total


def people_search(text, scope, limit=15):
    """Люди по ФИО (любая часть) или личному номеру, только в доступных округах. Старшие звания первыми."""
    text = str(text or '').strip()[:60]
    if not scope or not text:
        return []
    words = [w for w in text.split() if w][:3]
    where = ' AND '.join(['(full_name ILIKE %s OR personal_number ILIKE %s)'] * len(words))
    args = [x for w in words for x in (like(w), like(w))]
    return select(f'''SELECT {PEOPLE_COLUMNS}, district_code FROM registry_api.subunit_people
                      WHERE {where} AND district_code = ANY(%s::text[])
                      ORDER BY rank_order DESC, full_name LIMIT %s''', args + [list(scope), limit])


PEOPLE_GROUPS = {
    'category': 'rank_category', 'service': 'service_type', 'nationality': 'nationality', 'education': 'education',
    'rank': 'rank_name', 'marital': 'marital_status', 'fitness': 'fitness_category', 'blood': 'blood_group',
    'age': "CASE WHEN age < 21 THEN '18–20' WHEN age < 26 THEN '21–25' WHEN age < 31 THEN '26–30' "
           "WHEN age < 41 THEN '31–40' ELSE '41 и старше' END",
}


def people_stats(scope, group_by='category', code='', district=''):
    """Распределение личного состава (подразделение с подчинёнными, округ или все доступные округа):
    [{'value', 'people', 'avg_age'}], отсортировано по числу людей."""
    if not scope:
        return []
    expr = PEOPLE_GROUPS.get(group_by, PEOPLE_GROUPS['category'])
    where, args = 'district_code = ANY(%s::text[])', [list(scope)]
    if district:
        where += ' AND district_code = %s'
        args.append(district)
    if code:
        where += ' AND (subunit_code = %s OR subunit_code LIKE %s)'
        args += [code, like_prefix(code)]
    return select(f'''SELECT {expr} AS value, count(*) AS people, round(avg(age), 1) AS avg_age
                      FROM registry_api.subunit_people WHERE {where}
                      GROUP BY 1 ORDER BY 2 DESC, 1''', args)


def catalog_categories():
    return select(f'''SELECT category, count(*) AS items FROM registry_api.items WHERE {OWN_ITEMS}
                      GROUP BY 1 ORDER BY 1''')


def catalog_items(category):
    return select(f'''SELECT item_sname, item_name, unit_measure FROM registry_api.items
                      WHERE category ILIKE %s AND {OWN_ITEMS} ORDER BY item_sname''', [like(category)])


def get_person(personal_number, scope):
    """Карточка человека — только если его округ в области доступа пользователя."""
    if not scope:
        return None
    rows = select('SELECT * FROM registry_api.subunit_people WHERE personal_number = %s AND district_code = ANY(%s::text[])',
                  [str(personal_number)[:20], list(scope)])
    return rows[0] if rows else None


def unit_equipment(code, scope):
    """Техника и вооружение подразделения или соединения вместе с подчинёнными."""
    if not scope:
        return []
    return select('''SELECT item_sname, item_name, category, sum(qty) AS qty, unit_measure,
                            string_agg(DISTINCT source_code, ', ') AS sources, max(confidence) AS confidence
                     FROM registry_api.subunit_equipment
                     WHERE (subunit_code = %s OR subunit_code LIKE %s) AND district_code = ANY(%s::text[])
                     GROUP BY item_sname, item_name, category, unit_measure
                     ORDER BY category, sum(qty) DESC, item_sname''', [code, like_prefix(code), list(scope)])


def norm_sources():
    return select('SELECT source_code, title, url, confidence FROM registry_api.norm_sources ORDER BY confidence, source_code')


LEVELS = ('батальон', 'рота', 'взвод', 'отделение')
LEVEL_PLURAL = {'батальон': 'Батальонов', 'рота': 'Рот', 'взвод': 'Взводов', 'отделение': 'Отделений'}


def subunit_nav(rows, code=None):
    """Для страницы соединения (code=None) или подразделения: сам узел, путь от батальона, дети с подсчётом
    подчинённых по уровням. Возвращает None, если подразделения нет в этом соединении."""
    by_code = {r['subunit_code']: r for r in rows}
    if code is not None and code not in by_code:
        return None
    path = []
    cur = by_code.get(code)
    while cur:
        path.insert(0, cur)
        cur = by_code.get(cur['parent_code'])

    def below(c):
        counts = dict.fromkeys(LEVELS, 0)
        stack = [r for r in rows if r['parent_code'] == c]
        while stack:
            r = stack.pop()
            if r['level'] in counts:                    # «управление» в подсчёт уровней не входит
                counts[r['level']] += 1
            stack.extend(x for x in rows if x['parent_code'] == r['subunit_code'])
        return counts

    children = [dict(r, below=below(r['subunit_code'])) for r in rows if r['parent_code'] == code]
    # колонки таблицы детей: уровни ниже самого старшего из детей (у батальонов — роты, взводы, отделения).
    # Дети бывают разных уровней: у бригады — управление, батальоны, роты и взводы бригадного подчинения.
    child_levels = {c['level'] for c in children}
    ranked = [lv for lv in LEVELS if lv in child_levels]
    child_level = (ranked[0] if len(child_levels) == 1 else 'mixed') if children else None
    cols = list(LEVELS[LEVELS.index(ranked[0]) + 1:]) if ranked else []
    for ch in children:
        ch['counts'] = [ch['below'][lv] for lv in cols]
    total = below(code)
    return {'node': by_code.get(code), 'path': path[:-1] if code else [], 'children': children,
            'child_level': child_level, 'cols': [LEVEL_PLURAL[lv] for lv in cols],
            'stats': [(LEVEL_PLURAL[lv], total[lv]) for lv in LEVELS if total[lv]]}


def subunit_tree(rows):
    """Плоский список подразделений -> дерево: у каждого узла ключ 'children'."""
    nodes = {r['subunit_code']: dict(r, children=[]) for r in rows}
    roots = []
    for r in rows:
        node = nodes[r['subunit_code']]
        parent = nodes.get(r['parent_code'])
        (parent['children'] if parent else roots).append(node)
    return roots


def strength(code, scope):
    if code not in scope:
        return []
    return select('''SELECT category, personnel, origin, confidence FROM registry_api.district_strength
                     WHERE district_code = %s
                     ORDER BY array_position(ARRAY['офицеры', 'сержанты', 'солдаты'], category)''', [code])


def equipment_categories(code, scope):
    if code not in scope:
        return []
    return select('''SELECT category, count(*) AS items, sum(qty) AS units FROM registry_api.district_equipment
                     WHERE district_code = %s GROUP BY category ORDER BY category''', [code])


def equipment(code, scope, category='', term='', page=1):
    """Возвращает (строки страницы, всего строк)."""
    if code not in scope:
        return [], 0
    page, offset = page_bounds(page)
    where = 'district_code = %s AND (%s = \'\' OR category = %s) AND (item_sname ILIKE %s OR item_name ILIKE %s)'
    args = [code, category, category, like(term), like(term)]
    total = select(f'SELECT count(*) AS n FROM registry_api.district_equipment WHERE {where}', args)[0]['n']
    rows = select(f'''SELECT item_sname, item_name, category, qty, unit_measure, origin, confidence
                      FROM registry_api.district_equipment WHERE {where}
                      ORDER BY category, qty DESC, item_sname LIMIT %s OFFSET %s''', args + [PAGE_SIZE, offset])
    return rows, total


def supply(code, scope, category='', only_deficit=False, page=1):
    """Возвращает (строки страницы, всего строк)."""
    if code not in scope:
        return [], 0
    page, offset = page_bounds(page)
    where = 'district_code = %s AND (%s = \'\' OR category = %s) AND (NOT %s OR deficit > 0)'
    args = [code, category, category, bool(only_deficit)]
    total = select(f'SELECT count(*) AS n FROM registry_api.district_supply WHERE {where}', args)[0]['n']
    rows = select(f'''SELECT item_sname, item_name, category, norm_qty, stock_qty, deficit, provision_pct,
                             unit_measure, origin, confidence
                      FROM registry_api.district_supply WHERE {where}
                      ORDER BY provision_pct NULLS LAST, item_sname LIMIT %s OFFSET %s''', args + [PAGE_SIZE, offset])
    return rows, total


def supply_categories(code, scope):
    if code not in scope:
        return []
    return select('''SELECT category, count(*) AS items, count(*) FILTER (WHERE deficit > 0) AS deficit_items,
                            round(100 * avg(least(stock_qty / nullif(norm_qty, 0), 1)), 1) AS provision_pct
                     FROM registry_api.district_supply WHERE district_code = %s
                     GROUP BY category ORDER BY category''', [code])


def compare(scope, metric):
    """Один показатель по всем доступным округам. metric — ключ из METRICS."""
    if not scope or metric not in METRICS:
        return []
    column = METRICS[metric][0]          # имя колонки из фиксированного списка, не из ввода
    return select(f'''SELECT district_code, short_name, side, {column} AS value
                      FROM registry_api.districts WHERE district_code = ANY(%s::text[])
                      ORDER BY {column} DESC NULLS LAST, sort_order''', [list(scope)])


def item_holders(item_sname, scope):
    """В каких доступных округах числится образец."""
    if not scope:
        return []
    return select('''SELECT e.district_code, d.short_name, e.qty, e.unit_measure
                     FROM registry_api.district_equipment e JOIN registry_api.districts d USING (district_code)
                     WHERE e.item_sname = %s AND e.district_code = ANY(%s::text[])
                     ORDER BY e.qty DESC''', [item_sname, list(scope)])


# ---------------------------------------------------------------- каталог имущества (общий справочник)
# Сайт ORDA показывает только образцы своей армии: техника условного противника (США) остаётся в базе
# для основной версии, но в каталог, поиск и карточки здесь не попадает.
OWN_ITEMS = "coalesce(manufacturer_country, '') <> 'США'"


def item_catalog(term='', page=1):
    """Возвращает (строки страницы, всего строк)."""
    page, offset = page_bounds(page)
    pat = like(term)
    where = f'(item_sname ILIKE %s OR item_name ILIKE %s OR category ILIKE %s) AND {OWN_ITEMS}'
    total = select(f'SELECT count(*) AS n FROM registry_api.items WHERE {where}', [pat, pat, pat])[0]['n']
    rows = select(f'''SELECT item_sname, item_name, category, unit_measure FROM registry_api.items
                      WHERE {where} ORDER BY category, item_sname LIMIT %s OFFSET %s''',
                  [pat, pat, pat, PAGE_SIZE, offset])
    return rows, total


def find_items(text, limit=8):
    """Поиск образца по сокращению, названию или синониму («бензин» -> АИ-92)."""
    text = text.strip()[:90]
    if not text:
        return []
    pat = like(text)
    return select(f'''SELECT DISTINCT i.item_sname, i.item_name, i.category, i.unit_measure,
                             (lower(i.item_sname) = lower(%s) OR lower(a.alias) = lower(%s)) AS exact
                      FROM registry_api.items i LEFT JOIN registry_api.item_aliases a USING (item_sname)
                      WHERE (i.item_sname ILIKE %s OR i.item_name ILIKE %s OR a.alias ILIKE %s) AND coalesce(i.manufacturer_country, '') <> 'США'
                      ORDER BY exact DESC, i.item_sname LIMIT %s''', [text, text, pat, pat, pat, limit])


def get_item(item_sname):
    rows = select(f'''SELECT item_sname, item_name, category, manufacturer_country, unit_measure
                      FROM registry_api.items WHERE item_sname = %s AND {OWN_ITEMS}''', [item_sname])
    return rows[0] if rows else None


def item_specs(item_sname):
    # «этап 71» — служебная метка сборки каталога, на странице её не показываем
    return select('''SELECT param_name, value_num, value_text, unit, confidence, source_code, source_name,
                            NULLIF(note, 'этап 71') AS note
                     FROM registry_api.item_specs WHERE item_sname = %s ORDER BY param_name, confidence''', [item_sname])
