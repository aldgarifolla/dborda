"""Инструменты помощника. Каждый инструмент — функция repository.py с проверкой области доступа.

Описание (name, description, parameters) дано в виде JSON Schema: его можно без изменений
передать любой модели с поддержкой вызова инструментов. Результат инструмента — словарь
{'title', 'columns', 'rows', 'source', 'note'}; в нём только учебные данные из registry_api.
"""
import re

from .. import repository as repo

MAX_ROWS = 15
DISTRICT_PARAM = {'type': 'string', 'description': 'Код округа, например ОКР-АСТ'}


# Коды латиницей (английский вопрос: «brigade YUG-3», «OKR-AST») -> кириллица, как в базе.
LATIN_CODES = {'OKR': 'ОКР', 'AST': 'АСТ', 'VOS': 'ВОС', 'ZAP': 'ЗАП', 'YUG': 'ЮГ', 'YUZ': 'ЮГ'}
LATIN_CODE_RE = re.compile(r'(?<![A-Za-z])(OKR|AST|VOS|ZAP|YUG|YUZ)(?![A-Za-z])', re.IGNORECASE)
CODE_PARAMS = ('district', 'formation', 'unit')


def cyrillic_codes(text):
    return LATIN_CODE_RE.sub(lambda m: LATIN_CODES[m.group(1).upper()], str(text))


class ToolError(Exception):
    """Отказ инструмента: нет доступа, нет такого округа или неверные параметры."""


def _district(scope, code):
    """Код из scope без учёта регистра: модель может прислать «окр-аст» или «Окр-Аст»."""
    text = str(code or '').strip()
    by_fold = {c.casefold(): c for c in scope}
    if text.casefold() not in by_fold:
        raise ToolError(f'Округ «{text or "не указан"}» недоступен или не существует.')
    return by_fold[text.casefold()]


def _table(title, columns, rows, source, note=''):
    return {'title': title, 'columns': columns, 'rows': [[r.get(k) for k, _ in columns] for r in rows[:MAX_ROWS]],
            'headers': [h for _, h in columns], 'source': source,
            'note': note or (f'Показаны первые {MAX_ROWS} строк из {len(rows)}.' if len(rows) > MAX_ROWS else '')}


def list_districts(scope):
    rows = repo.list_districts(scope)
    return _table('Доступные округа', [('district_code', 'Код'), ('short_name', 'Округ'), ('hq_city', 'Штаб'),
                                       ('formations', 'Соединений'), ('personnel_total', 'Численность')],
                  rows, 'registry_api.districts')


def district_summary(scope, district):
    code = _district(scope, district)
    d = repo.get_district(code, scope)
    rows = [{'k': 'Полное название', 'v': d['full_name']}, {'k': 'Штаб', 'v': d['hq_city']},
            {'k': 'Зона ответственности', 'v': d['zone_note']},
            {'k': 'Соединений', 'v': d['formations']}, {'k': 'Численность, чел.', 'v': d['personnel_total']}]
    rows += [{'k': f'  в том числе {s["category"]}', 'v': s['personnel']} for s in repo.strength(code, scope)]
    rows += [{'k': 'Образцов техники и вооружения', 'v': d['equipment_items']},
             {'k': 'Единиц техники и вооружения', 'v': d['equipment_units']},
             {'k': 'Обеспеченность запасами, %', 'v': d['supply_pct']}]
    return _table(f'Сводка — {d["short_name"]}', [('k', 'Показатель'), ('v', 'Значение')], rows,
                  'registry_api.districts, registry_api.district_strength')


def district_formations(scope, district):
    code = _district(scope, district)
    rows = repo.formations(code, scope)
    if rows:   # итог по округу считает код, а не модель
        rows = rows + [{'formation_code': '', 'formation_name': 'Итого по округу',
                        'formation_type': f'{len(rows)} соединения',
                        **{k: sum(r[k] or 0 for r in rows) for k in ('battalions', 'companies', 'platoons', 'squads')}}]
    return _table(f'Состав — {code}', [('formation_code', 'Код'), ('formation_name', 'Соединение'), ('formation_type', 'Тип'),
                                        ('battalions', 'Батальонов'), ('companies', 'Рот'), ('platoons', 'Взводов'),
                                        ('squads', 'Отделений')],
                  rows, 'registry_api.district_formations')


def formation_structure(scope, formation):
    """Батальоны и роты соединения с числом взводов и отделений."""
    code = str(formation or '').strip().upper()[:20]
    found = repo.get_formation(code, scope)
    if not found:
        raise ToolError(f'Соединение «{code or "не указано"}» недоступно или не существует.')
    rows = []
    for bn in repo.subunit_tree(repo.subunits(code, scope)):
        rows.append({'name': f'{bn["subunit_name"]} ({bn["subunit_code"]})', 'level': bn['level'], 'personnel': bn.get('personnel'),
                     'platoons': sum(len(c['children']) for c in bn['children']),
                     'squads': sum(len(p['children']) for c in bn['children'] for p in c['children'])})
        for co in bn['children']:
            if bn['level'] != 'батальон':
                break                                  # у бригадных рот взводы не перечисляем
            rows.append({'name': f'  {co["subunit_name"]} ({co["subunit_code"]})', 'level': co['level'], 'personnel': co.get('personnel'),
                         'platoons': len(co['children']),
                         'squads': sum(len(p['children']) for p in co['children'])})
    table = _table(f'Структура — {found["formation_code"]} ({found["district_name"]})',
                   [('name', 'Подразделение'), ('level', 'Уровень'), ('personnel', 'Личный состав'),
                    ('platoons', 'Взводов'), ('squads', 'Отделений')],
                   rows, 'registry_api.district_subunits')
    table['note'] = (f'Итого: {found["battalions"]} батальона, {found["companies"]} рот, {found["platoons"]} взводов, '
                     f'{found["squads"]} отделений; личный состав {found.get("personnel")} чел., '
                     f'техника {found.get("equipment_units")} ед. (учебный шаблон, C).')
    return table


def district_equipment(scope, district, category='', search=''):
    code = _district(scope, district)
    if not category and not search:
        return _table(f'Техника и вооружение по категориям — {code}',
                      [('category', 'Категория'), ('items', 'Образцов'), ('units', 'Единиц')],
                      repo.equipment_categories(code, scope), 'registry_api.district_equipment')
    rows, total = repo.equipment(code, scope, category=str(category)[:120], term=str(search)[:90])
    return _table(f'Техника и вооружение — {code}', [('item_sname', 'Образец'), ('category', 'Категория'),
                                                     ('qty', 'Кол-во'), ('unit_measure', 'Ед.')],
                  rows, 'registry_api.district_equipment', f'Всего строк: {total}.' if total > MAX_ROWS else '')


def district_supply(scope, district, category='', only_deficit=False):
    code = _district(scope, district)
    if not category and not only_deficit:
        table = _table(f'Запасы по категориям — {code}',
                       [('category', 'Категория'), ('items', 'Позиций'), ('deficit_items', 'С дефицитом'),
                        ('provision_pct', 'Обеспеченность, %')],
                       repo.supply_categories(code, scope), 'registry_api.district_supply')
        d = repo.get_district(code, scope)
        if d and d.get('supply_pct') is not None:   # общий показатель округа считает база, не модель
            table['note'] = f'Средняя обеспеченность запасами по округу: {d["supply_pct"]} %. ' + table['note']
        return table
    rows, total = repo.supply(code, scope, category=str(category)[:120], only_deficit=bool(only_deficit))
    return _table(f'Запасы — {code}', [('item_sname', 'Позиция'), ('item_name', 'Наименование'),
                                       ('norm_qty', 'Норма'), ('stock_qty', 'Наличие'),
                                       ('deficit', 'Дефицит'), ('provision_pct', '%'), ('unit_measure', 'Ед.')],
                  rows, 'registry_api.district_supply', f'Всего строк: {total}.' if total > MAX_ROWS else '')


def compare_districts(scope, metric):
    if metric not in repo.METRICS:
        raise ToolError('Неизвестный показатель. Доступны: ' + ', '.join(repo.METRICS))
    rows = repo.compare(scope, metric)
    table = _table(f'Сравнение округов: {repo.METRICS[metric][1]}',
                   [('district_code', 'Код'), ('short_name', 'Округ'), ('value', repo.METRICS[metric][1])],
                   rows, 'registry_api.districts')
    ranked = [r for r in rows if r['value'] is not None]
    if len(ranked) > 1:   # максимум и минимум считает код, а не модель
        top, low = max(ranked, key=lambda r: r['value']), min(ranked, key=lambda r: r['value'])
        table['note'] = (f'Больше всего: {top["short_name"]} — {top["value"]}. '
                         f'Меньше всего: {low["short_name"]} — {low["value"]}.')
    return table


# Обозначения образцов латиницей (английский вопрос: «BMP-2», «T-72B», «AK-74M») -> кириллица, как в каталоге.
# Применяется только если по исходному написанию ничего не нашлось: в каталоге есть и настоящие латинские
# названия (M1A2 Abrams, Javelin).
LATIN_DIGRAPHS = (('SHCH', 'Щ'), ('ZH', 'Ж'), ('KH', 'Х'), ('CH', 'Ч'), ('SH', 'Ш'), ('YU', 'Ю'), ('YA', 'Я'), ('TS', 'Ц'))
LATIN_LETTERS = dict(zip('ABVGDEZIJKLMNOPRSTUFHCY', 'АБВГДЕЗИЙКЛМНОПРСТУФХЦЫ'))
LATIN_TOKEN = re.compile(r'(?<![A-Za-z])[A-Za-z]{1,4}(?![A-Za-z])')


def cyrillic_item(text):
    """«BMP-2» -> «БМП-2», «T-72B» -> «Т-72Б», «ak-74m» -> «АК-74М». Слова длиннее 4 букв не трогаются."""
    def convert(m):
        word = m.group(0).upper()
        for lat, cyr in LATIN_DIGRAPHS:
            word = word.replace(lat, cyr)
        return ''.join(LATIN_LETTERS.get(ch, ch) for ch in word)
    return LATIN_TOKEN.sub(convert, str(text))


def _items(text, limit=None):
    found = repo.find_items(str(text)) if limit is None else repo.find_items(str(text), limit=limit)
    if not found and cyrillic_item(text) != str(text):
        alt = cyrillic_item(text)
        found = repo.find_items(alt) if limit is None else repo.find_items(alt, limit=limit)
    return found


def find_item(scope, text):
    return _table(f'Поиск в каталоге: «{str(text)[:60]}»',
                  [('item_sname', 'Сокращение'), ('item_name', 'Наименование'), ('category', 'Категория')],
                  _items(text), 'registry_api.items, registry_api.item_aliases')


def item_card(scope, item):
    found = repo.get_item(str(item)[:200]) or repo.get_item(cyrillic_item(item)[:200])
    if not found:
        matches = _items(item, limit=1)
        found = repo.get_item(matches[0]['item_sname']) if matches else None
    if not found:
        raise ToolError(f'Образец «{str(item)[:60]}» в каталоге не найден.')
    rows = [{'k': 'Наименование', 'v': found['item_name'], 'c': '', 's': ''},
            {'k': 'Категория', 'v': found['category'], 'c': '', 's': ''}]
    for s in repo.item_specs(found['item_sname']):
        value = s['value_num'] if s['value_num'] is not None else s['value_text']
        rows.append({'k': s['param_name'], 'v': f'{value} {s["unit"] or ""}'.strip(), 'c': s['confidence'], 's': s['source_name'] or ''})
    for h in repo.item_holders(found['item_sname'], scope):
        rows.append({'k': f'В округе {h["short_name"]}', 'v': f'{h["qty"]} {h["unit_measure"] or ""}'.strip(), 'c': 'C', 's': 'учебная модель'})
    return _table(f'Карточка образца — {found["item_sname"]}',
                  [('k', 'Показатель'), ('v', 'Значение'), ('c', 'Достоверность'), ('s', 'Источник')],
                  rows, 'registry_api.items, registry_api.item_specs, registry_api.district_equipment')


def normalize_unit_code(unit):
    """Код подразделения от модели -> канонический. Номер батальона выводится из сквозного номера роты
    (Р8 -> Б3), поэтому «ВОС-1.Б2.Р8» и «ВОС-1.Р8» дают ВОС-1.Б3.Р8."""
    parts = [x for x in re.split(r'[.\s]+', str(unit or '').strip().upper()[:40]) if x]
    if not parts:
        return ''
    if any(not (x[:1] in 'БРВОBPO' and x[1:].isdigit()) for x in parts[1:]):
        return '.'.join(parts)                          # бригадные подразделения: ВОС-1.РР, ВОС-1.Б1.МБ.В2
    fixed, levels = [parts[0]], {}
    for x in parts[1:]:
        x = x.replace('B', 'В').replace('P', 'Р').replace('O', 'О')   # латиница вместо кириллицы
        if x[:1] in 'БРВО' and x[1:].isdigit():
            levels[x[0]] = int(x[1:])
    if 'Р' in levels:
        levels['Б'] = (levels['Р'] - 1) // 3 + 1
    for letter in 'БРВО':
        if letter not in levels:
            break
        fixed.append(f'{letter}{levels[letter]}')
    return '.'.join(fixed)


def unit_code_from_numbers(formation, battalion=None, company=None, platoon=None, squad=None):
    """Код из номеров. Рота — сквозной номер в бригаде (1–9) или номер внутри батальона, если батальон указан.
    Если указан только нижний уровень, недостающие старшие берутся первыми."""
    nums = [battalion, company, platoon, squad]
    nums = [int(x) if str(x).strip().isdigit() else None for x in nums]
    battalion, company, platoon, squad = nums
    deepest = max((i for i, x in enumerate(nums) if x), default=-1)
    if deepest < 0:
        return str(formation)
    if company and battalion and company <= 3:
        company = (battalion - 1) * 3 + company          # «2-я рота 3-го батальона» -> Р8
    if company and not battalion:
        battalion = (company - 1) // 3 + 1
    battalion = battalion or 1
    company = company or (battalion - 1) * 3 + 1
    parts = [str(formation), f'Б{battalion}', f'Р{company}', f'В{platoon or 1}', f'О{squad or 1}']
    return '.'.join(parts[:deepest + 2])


def find_unit_by_name(scope, formation, unit_name, battalion=None):
    """Подразделение бригады по названию («танковый батальон», «реактивный дивизион»,
    «разведывательная рота», «управление»), при необходимости — внутри батальона. Берётся самое старшее."""
    text = str(unit_name).casefold().replace('ё', 'е').replace('медпункт', 'медицинский пункт')
    # основа слова — первые ~70 % букв: «гранатометного» -> «гранатоме», «роты» -> «рот»
    words = [w[:max(3, int(len(w) * 0.7))] for w in re.findall(r'\w+', text) if len(w) > 2]
    if not words:
        return None
    prefix = f'{formation}.Б{battalion}.' if str(battalion or '').isdigit() else f'{formation}.'
    found = [r for r in repo.subunits(formation, scope)
             if r['subunit_code'].startswith(prefix)
             and all(w in r['subunit_name'].casefold().replace('ё', 'е') for w in words)]
    found.sort(key=lambda r: (r['subunit_code'].count('.'), r['subunit_code']))
    return found[0]['subunit_code'] if found else None


def search_total(stem, rows):
    """Итог по найденным образцам, если их несколько и единица одна: «Всего (танк): 62 шт. (54 + 8)».
    Слово должно начинаться с основы — «противотанковый» в итог по «танк» не попадает."""
    picked, unit = [], None
    for r in rows:
        name = r['k'].casefold().replace('ё', 'е')
        qty, _, measure = str(r['v']).partition(' ')
        if not qty.isdigit() or not any(w.startswith(stem) for w in re.findall(r'\w+', name)):
            continue
        if unit not in (None, measure):
            return ''
        unit = measure
        picked.append(int(qty))
    if len(picked) < 2:
        return ''
    return f'Всего ({stem}): {sum(picked)} {unit} ({" + ".join(map(str, picked))}).'.replace('  ', ' ')


def unit_composition(scope, formation='', battalion=None, company=None, platoon=None, squad=None, unit='', search='',
                     unit_name=''):
    """Личный состав, должности и техника бригады или любого её подразделения."""
    formation = str(formation or '').strip().upper()
    unit = str(unit or '').strip().upper().lstrip('.')
    if unit and formation and not unit.startswith(formation):
        unit = f'{formation}.{unit}'                    # модель прислала «У» или «Б1.МБ» отдельно от бригады
    if unit_name and formation:
        unit = find_unit_by_name(scope, formation, unit_name, battalion) or unit
        if not unit:
            raise ToolError(f'В {formation} нет подразделения «{unit_name}».')
    if unit:
        code = normalize_unit_code(unit)
    else:
        code = normalize_unit_code(unit_code_from_numbers(str(formation).strip().upper(), battalion, company, platoon, squad))
    formation_code = code.split('.')[0]
    formation = repo.get_formation(formation_code, scope)
    if not formation:
        raise ToolError(f'Подразделение «{code or "не указано"}» недоступно или не существует.')
    if code == formation_code:
        name, totals = formation['formation_name'], formation
    else:
        node = next((r for r in repo.subunits(formation_code, scope) if r['subunit_code'] == code), None)
        if not node:
            raise ToolError(f'Подразделение «{code}» не найдено в {formation_code}. Коды: батальоны Б1–Б3; роты сквозные — '
                            'в Б1 роты Р1–Р3, в Б2 Р4–Р6, в Б3 Р7–Р9; взводы В1–В3; отделения О1–О3.')
        name, totals = node['subunit_name'], node
    staff = repo.unit_staff(code, scope)
    equipment = repo.unit_equipment(code, scope)
    rows = [{'k': 'Личный состав, чел.', 'v': totals.get('personnel')},
            {'k': '  офицеров', 'v': totals.get('officers')}, {'k': '  сержантов', 'v': totals.get('sergeants')},
            {'k': '  солдат', 'v': totals.get('soldiers')},
            {'k': 'Техника (без стрелкового оружия), ед.', 'v': totals.get('equipment_units')}]
    rows += [{'k': f'Должность: {p["position_name"]} ({p["rank_name"]})', 'v': p['qty']} for p in staff[:8]]
    # сначала техника и тяжёлое вооружение целиком, затем стрелковое оружие
    heavy = [e for e in equipment if e['category'] != 'Стрелковое оружие и гранатомёты']
    light = [e for e in equipment if e['category'] == 'Стрелковое оружие и гранатомёты']
    rows += [{'k': f'Образец: {e["item_sname"]} — {e["item_name"]}', 'v': f'{e["qty"]} {e["unit_measure"] or ""}'.strip()}
             for e in heavy + light]
    needle = str(search or '').strip().casefold().replace('ё', 'е')[:40]
    if needle:   # вопрос про конкретный образец или должность: оставляем итоги и подходящие строки
        stem = needle[:max(4, len(needle) - 2)]                     # «миномётов» -> «миномет», «агс» -> «агс»
        found = [r for r in rows[5:] if stem in r['k'].casefold().replace('ё', 'е')]
        rows = rows[:5] + (found or [{'k': f'Строк со словом «{search}» нет', 'v': '—'}])
        total = search_total(stem, [r for r in found if r['k'].startswith('Образец:')])
    else:
        total = ''
    table = _table(f'Состав — {name} ({code})', [('k', 'Показатель'), ('v', 'Значение')], rows,
                   'registry_api.subunit_staff, registry_api.subunit_equipment')
    table['rows'] = [[r['k'], r['v']] for r in rows]
    table['note'] = (total + ' ' if total else '') + \
        'Типовой состав по открытым источникам и оценке составителя (не штат ВС РК), учебные данные.'
    return table


METRIC_PARAM = {'type': 'string', 'enum': list(repo.METRICS), 'description': 'personnel — численность, equipment — техника, supply — обеспеченность запасами, formations — число соединений'}
TOOLS = {
    'list_districts': (list_districts, 'Список округов (региональных командований), доступных пользователю.', {}, []),
    'district_summary': (district_summary, 'Сводка по округу: состав, численность по категориям, техника, обеспеченность.',
                         {'district': DISTRICT_PARAM}, ['district']),
    'district_formations': (district_formations, 'Соединения (бригады) в составе округа и число их батальонов, рот, взводов, отделений.',
                            {'district': DISTRICT_PARAM}, ['district']),
    'unit_composition': (unit_composition, 'Личный состав (офицеры, сержанты, солдаты), должности и техника бригады '
                         'или любого её подразделения вплоть до отделения. Укажи бригаду и номера нужных уровней; '
                         'для всей бригады — только formation.',
                         {'formation': {'type': 'string', 'description': 'Код бригады: АСТ-1…3, ВОС-1…3, ЗАП-1…3, ЮГ-1…3'},
                          'battalion': {'type': 'integer', 'description': 'Номер батальона (дивизиона) 1–3'},
                          'company': {'type': 'integer', 'description': 'Номер роты (батареи): сквозной 1–9 или 1–3 внутри батальона'},
                          'platoon': {'type': 'integer', 'description': 'Номер взвода 1–3 (в батарее 3 — взвод управления)'},
                          'squad': {'type': 'integer', 'description': 'Номер отделения (экипажа, расчёта) 1–3'},
                          'unit_name': {'type': 'string', 'description': 'Название батальона без номера, если он назван словами: '
                                                                         'танковый батальон, реактивный дивизион, ремонтный батальон'},
                          'unit': {'type': 'string', 'description': 'Готовый код, если он известен, например ВОС-1.Б3.Р8.В2'},
                          'search': {'type': 'string', 'description': 'Если спрашивают про конкретный образец или должность — '
                                                                      'слово из вопроса: танк, БМП, командир'}},
                         []),
    'formation_structure': (formation_structure, 'Структура одного соединения: батальоны и роты, число взводов и отделений.',
                            {'formation': {'type': 'string', 'description': 'Код соединения, например ВОС-1'}}, ['formation']),
    'district_equipment': (district_equipment, 'Техника и вооружение округа. Без параметров — итог по категориям.',
                           {'district': DISTRICT_PARAM, 'category': {'type': 'string', 'description': 'Точное название категории'},
                            'search': {'type': 'string', 'description': 'Часть названия образца'}}, ['district']),
    'district_supply': (district_supply, 'Запасы округа: норма, наличие, дефицит. Без параметров — итог по категориям.',
                        {'district': DISTRICT_PARAM, 'category': {'type': 'string'},
                         'only_deficit': {'type': 'boolean', 'description': 'Только позиции с дефицитом'}}, ['district']),
    'compare_districts': (compare_districts, 'Один показатель по всем доступным округам.', {'metric': METRIC_PARAM}, ['metric']),
    'find_item': (find_item, 'Поиск образца в каталоге по названию или синониму.', {'text': {'type': 'string'}}, ['text']),
    'item_card': (item_card, 'Характеристики образца с источниками и уровнем достоверности.', {'item': {'type': 'string'}}, ['item']),
}


def schemas():
    """Описания инструментов в формате JSON Schema для модели с вызовом инструментов."""
    return [{'name': name, 'description': desc,
             'input_schema': {'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}}
            for name, (_, desc, props, required) in TOOLS.items()]


def run(name, args, scope):
    """Выполняет инструмент. Неизвестные имена и лишние параметры отклоняются."""
    if name not in TOOLS:
        raise ToolError(f'Инструмент «{name}» не существует.')
    func, _, props, required = TOOLS[name]
    args = dict(args or {})
    for key in CODE_PARAMS:
        if isinstance(args.get(key), str):
            args[key] = cyrillic_codes(args[key])
    extra = set(args) - set(props)
    missing = [p for p in required if args.get(p) in (None, '')]
    if extra or missing:
        raise ToolError('Неверные параметры инструмента ' + name)
    return func(scope, **args)
