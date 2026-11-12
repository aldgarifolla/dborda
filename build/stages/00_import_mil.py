"""Импорт Excel-выгрузок «Военной БД» в PostgreSQL: очистка, нормализация, загрузка и сверка.

Источники (папка --src):
  brigade_все_данные.xlsx      — первая выгрузка (только свои + омбр из ПМИ, есть ID людей и предметов, уровни, звания)
  military_db_v2_обзор.xlsx    — расширенная выгрузка (+ бригады США, ТТХ, источники, посадка, SIPRI)

Что попадает в mil_core: только первичные факты. Сводные листы («… по уровням», «Численность», «Горючее»,
«Боекомплект», «Структура» с численностью «с подчинёнными») не грузятся как факты: из них вычисляется
собственное значение подразделения (итог минус дети), а после загрузки они используются для сверки.

Запуск:
  python import_mil.py --src input --out out --dry-run
  python import_mil.py --src input --out out --dsn postgresql://user@host/db --init-schema schema_mil.sql
"""
import argparse, json, os, re, sys, datetime as dt
from collections import Counter, defaultdict, deque
import pandas as pd
from openpyxl import load_workbook

V1, V2 = 'brigade_все_данные', 'military_db_v2_обзор'

# ============================================================== чтение
def read_book(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    out = {}
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        header = [str(h).strip() if h is not None else f'col{i}' for i, h in enumerate(rows[0])]
        recs = []
        for n, r in enumerate(rows[1:], start=2):
            if all(v in (None, '') for v in r):
                continue
            d = dict(zip(header, r)); d['_row'] = n
            recs.append(d)
        out[ws.title] = recs
    return out


def find_file(src, stem):
    for f in os.listdir(src):
        if f.startswith(stem) and f.endswith('.xlsx'):
            return f
    sys.exit(f'нет файла {stem}*.xlsx в {src}')


# ============================================================== очистка
def t(v):
    if v is None:
        return None
    s = re.sub(r'\s+', ' ', str(v)).strip()
    return s or None


def code(v):
    s = t(v)
    if not s:
        return None
    s = s.replace(' ', '')
    return s if s.endswith('.') else s + '.'


def parent_of(c):
    return c[:c[:-1].rfind('.') + 1] or None if c.count('.') > 1 else None


def num(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(' ', '').replace(',', '.'))
    except ValueError:
        return None


def to_int(v):
    x = num(v)
    return int(round(x)) if x is not None else None


class Log:
    def __init__(self):
        self.rows = []

    def add(self, entity, sev, file, sheet, row, reason, raw=None):
        self.rows.append({'entity': entity, 'severity': sev, 'src_file': file, 'src_sheet': sheet, 'src_row': row, 'reason': reason,
                          'raw': {k: (str(v) if v is not None else None) for k, v in (raw or {}).items() if k != '_row'}})


# ============================================================== сборка
def build(src):
    f1, f2 = find_file(src, V1), find_file(src, V2)
    b1, b2 = read_book(os.path.join(src, f1)), read_book(os.path.join(src, f2))
    log = Log()
    C = {}

    # ---- источники
    C['source'] = [{'source_code': t(r['Код']), 'source_name': t(r['Источник']), 'publisher': t(r['Издатель']), 'url': t(r['URL']),
                    'source_type': t(r['Тип']), 'license': t(r['Лицензия']),
                    'accessed_on': dt.date.fromisoformat(str(r['Дата обращения'])[:10]) if r['Дата обращения'] else None}
                   for r in b2['Источники']]
    src_by_name = {s['source_name']: s['source_code'] for s in C['source']}

    # ---- уровни
    C['unit_level'], seen_l = [], {}
    for r in b1['Уровни']:
        n = t(r['Уровень'])
        if n in seen_l:
            log.add('unit_level', 'warning', f1, 'Уровни', r['_row'], f'«{n}» повторяется под ID {to_int(r["ID"])} и {seen_l[n]} — оставлен ID {seen_l[n]}', r); continue
        seen_l[n] = to_int(r['ID'])
        C['unit_level'].append({'level_id': to_int(r['ID']), 'level_name': n})
    levels = {l['level_name'] for l in C['unit_level']}

    # ---- каталог: v2 полнее, v1 даёт legacy ID; сверяем, что пересечение совпадает
    legacy = {}
    for r in b1['Каталог ВВТ и имущества']:
        legacy[t(r['Сокращённое'])] = (to_int(r['ID']), t(r['Полное']), t(r['Категория']), t(r['Ед.']))
    items, by_full = {}, {}
    for r in b2['Каталог ВВТ и имущества']:
        s, full = t(r['Сокращённое']), t(r['Полное'])
        if s in items:
            log.add('item', 'error', f2, 'Каталог ВВТ и имущества', r['_row'], f'дубль сокращённого наименования «{s}»', r); continue
        lg = legacy.get(s)
        if lg and (lg[1], lg[2], lg[3]) != (full, t(r['Категория']), t(r['Ед.'])):
            log.add('item', 'warning', f2, 'Каталог ВВТ и имущества', r['_row'], f'«{s}» отличается от первой выгрузки: {lg[1:]}', r)
        items[s] = {'item_sname': s, 'item_name': full, 'category': t(r['Категория']), 'country': t(r['Страна']),
                    'unit_measure': t(r['Ед.']), 'legacy_id': lg[0] if lg else None}
        if full in by_full:
            log.add('item', 'error', f2, 'Каталог ВВТ и имущества', r['_row'], f'дубль полного наименования «{full}»', r)
        by_full[full] = s
    for s in legacy:
        if s not in items:
            log.add('item', 'warning', f1, 'Каталог ВВТ и имущества', None, f'«{s}» есть только в первой выгрузке — добавлен')
            lg = legacy[s]
            items[s] = {'item_sname': s, 'item_name': lg[1], 'category': lg[2], 'country': None, 'unit_measure': lg[3], 'legacy_id': lg[0]}
            by_full[lg[1]] = s
    C['item'] = list(items.values())
    if any(s != t(s) for s in items):
        pass
    double_spaces = sum(1 for r in b2['Каталог ВВТ и имущества'] for k in ('Сокращённое', 'Полное') if r[k] and '  ' in str(r[k]))
    if double_spaces:
        log.add('item', 'info', f2, 'Каталог ВВТ и имущества', None, f'двойные пробелы в наименованиях схлопнуты: {double_spaces} значений (одинаково во всех листах)')

    # ---- подразделения: Структура (все), численность «с подчинёнными» → своя
    side_v1 = {code(r['Код']): t(r['Сторона']) for r in b1['Структура']}
    units, tot, est = {}, {}, {}
    for r in b2['Структура (все)']:
        c = code(r['Код'])
        if not c or not re.match(r'^(\d+\.)+$', c):
            log.add('unit', 'error', f2, 'Структура (все)', r['_row'], f'неверный код «{r["Код"]}»', r); continue
        if c in units:
            log.add('unit', 'error', f2, 'Структура (все)', r['_row'], f'дубль кода {c}', r); continue
        lvl = t(r['Уровень'])
        if lvl and lvl not in levels:
            log.add('unit', 'warning', f2, 'Структура (все)', r['_row'], f'уровень «{lvl}» нет в справочнике — NULL', r); lvl = None
        country = t(r['Страна'])
        side = side_v1.get(c) or ('свои' if country == 'РФ' else 'противник')
        units[c] = {'unit_code': c, 'parent_code': parent_of(c), 'short_name': t(r['Подразделение']), 'full_name': t(r['Полное наименование']),
                    'level_name': lvl, 'country': country, 'side': side, 'confidence': t(r['Достоверность']),
                    'personnel_own': 0, 'personnel_own_estimated': 0, 'sort_order': len(units) + 1}
        tot[c], est[c] = to_int(r['Л/с (с подчин.)']) or 0, to_int(r['Из них оценка']) or 0
    for c in side_v1:
        if c not in units:
            log.add('unit', 'error', f1, 'Структура', None, f'подразделение {c} есть только в первой выгрузке')
    kids = defaultdict(list)
    for c, u in units.items():
        if u['parent_code'] and u['parent_code'] not in units:
            log.add('unit', 'warning', f2, 'Структура (все)', None, f'вышестоящее {u["parent_code"]} для {c} отсутствует — NULL'); u['parent_code'] = None
        if u['parent_code']:
            kids[u['parent_code']].append(c)
    for c, u in units.items():
        own = tot[c] - sum(tot[k] for k in kids[c])
        own_e = est[c] - sum(est[k] for k in kids[c])
        if own < 0 or own_e < 0:
            log.add('unit', 'error', f2, 'Структура (все)', None, f'{c}: численность меньше суммы подчинённых ({tot[c]})')
            own, own_e = max(own, 0), max(own_e, 0)
        u['personnel_own'], u['personnel_own_estimated'] = own, own_e
    C['unit'] = sorted(units.values(), key=lambda u: u['sort_order'])

    # ---- звания: РФ — справочник v1, США — из штата v2
    ranks = {t(r['Звание']): {'rank_name': t(r['Звание']), 'category': t(r['Категория']), 'army': 'РФ', 'sort_order': to_int(r['ID'])} for r in b1['Звания']}
    # ---- должности и штат
    positions, staff = {}, []
    seq = Counter()
    army_of_pos = {}
    for r in b2['Табель по должностям']:
        army_of_pos[t(r['Должность'])] = t(r['Армия'])
    for r in b2['Штат (все)']:
        c, pos, rk, cat = code(r['Код']), t(r['Должность']), t(r['Звание']), t(r['Категория'])
        if c not in units:
            log.add('staff', 'error', f2, 'Штат (все)', r['_row'], f'подразделение {c} нет в структуре', r); continue
        army = units[c]['country']
        if rk not in ranks:
            if army == 'РФ':
                log.add('staff', 'error', f2, 'Штат (все)', r['_row'], f'звание «{rk}» нет в справочнике званий', r); continue
            ranks[rk] = {'rank_name': rk, 'category': cat, 'army': 'США', 'sort_order': None}
        elif ranks[rk]['category'] != cat:
            log.add('staff', 'warning', f2, 'Штат (все)', r['_row'], f'категория «{cat}» не совпадает со справочником «{ranks[rk]["category"]}»', r)
        positions.setdefault(pos, {'position_name': pos, 'army': army_of_pos.get(pos, army)})
        seq[c] += 1
        parts = (t(r['ФИО']) or '').split(' ')
        staff.append({'unit_code': c, 'seq': seq[c], 'position_name': pos, 'rank_name': rk, 'fio': t(r['ФИО']),
                      'last_name': parts[0] if parts[0] else None, 'first_name': parts[1] if len(parts) > 1 else None,
                      'patronymic': ' '.join(parts[2:]) or None if len(parts) > 2 else None, '_row': r['_row']})
    # стабильный штатный id = порядковый номер строки
    for i, s in enumerate(staff, 1):
        s['staff_id'] = i
    # ID людей из первой выгрузки: сопоставление по (код, должность, звание, ФИО), с учётом повторов
    pool = defaultdict(deque)
    for r in b1['Штат и л_с']:
        pool[(code(r['Код']), t(r['Должность']), t(r['Звание']), t(r['ФИО']))].append((to_int(r['ID']), r['_row']))
    people = []
    for s in staff:
        if s['fio']:
            q = pool.get((s['unit_code'], s['position_name'], s['rank_name'], s['fio']))
            if q:
                pid, _ = q.popleft()
                s['person_id'] = pid
                people.append({'person_id': pid, 'last_name': s['last_name'], 'first_name': s['first_name'], 'patronymic': s['patronymic']})
            else:
                s['person_id'] = None
                log.add('staff', 'warning', f2, 'Штат (все)', s['_row'], f'ФИО «{s["fio"]}» не найдено в первой выгрузке — без ID')
        else:
            s['person_id'] = None
    left = sum(len(q) for q in pool.values())
    if left:
        log.add('staff', 'warning', f1, 'Штат и л_с', None, f'{left} человек из первой выгрузки не нашлись во второй')
    C['rank'], C['position'], C['person'] = list(ranks.values()), list(positions.values()), people
    C['staff_position'] = [{k: s[k] for k in ('staff_id', 'unit_code', 'seq', 'position_name', 'rank_name', 'person_id')} for s in staff]

    # ---- комплекты и табель
    kits, kit_items = {}, {}
    for r in b2['Комплекты']:
        k, name, it = t(r['Код']), t(r['Комплект']), t(r['Предмет'])
        kits.setdefault(k, {'kit_code': k, 'kit_name': name, 'army': t(r['Армия'])})
        s = by_full.get(it)
        if not s:
            log.add('kit', 'error', f2, 'Комплекты', r['_row'], f'предмет «{it}» нет в каталоге', r); continue
        kit_items[(k, s)] = {'kit_code': k, 'item_sname': s, 'qty': to_int(r['Кол-во'])}
    kit_by_name = {k['kit_name']: k['kit_code'] for k in kits.values()}
    pk, table_items = set(), defaultdict(dict)
    for r in b2['Табель по должностям']:
        pos, kn, it, q = t(r['Должность']), t(r['Комплект']), t(r['Предмет']), to_int(r['Кол-во'])
        kc = kit_by_name.get(kn)
        if not kc:
            log.add('position_kit', 'error', f2, 'Табель по должностям', r['_row'], f'комплект «{kn}» нет в листе Комплекты', r); continue
        if pos not in positions:
            positions[pos] = {'position_name': pos, 'army': t(r['Армия'])}
            log.add('position_kit', 'info', f2, 'Табель по должностям', r['_row'], f'должность «{pos}» есть в табеле, но не в штате')
        pk.add((pos, kc))
        table_items[(pos, kc)][by_full.get(it)] = q
    # табель должен повторять состав комплекта
    kit_content = defaultdict(dict)
    for (k, s), v in kit_items.items():
        kit_content[k][s] = v['qty']
    bad = [(p, k) for (p, k), d in table_items.items() if d != kit_content[k]]
    for p, k in bad[:20]:
        log.add('position_kit', 'error', f2, 'Табель по должностям', None, f'состав «{k}» у «{p}» не совпадает с листом Комплекты')
    C['kit'], C['kit_item'] = list(kits.values()), list(kit_items.values())
    C['position'] = list(positions.values())
    C['position_kit'] = [{'position_name': p, 'kit_code': k} for p, k in sorted(pk)]

    # ---- ТТХ
    params, specs = {}, []
    for r in b2['ТТХ с источниками']:
        s, p, v = t(r['ВВТ']), t(r['Параметр']), t(r['Значение'])
        if s not in items:
            log.add('item_spec', 'error', f2, 'ТТХ с источниками', r['_row'], f'«{s}» нет в каталоге', r); continue
        sc = src_by_name.get(t(r['Источник']))
        if not sc:
            log.add('item_spec', 'error', f2, 'ТТХ с источниками', r['_row'], f'источник «{r["Источник"]}» нет в листе Источники', r); continue
        params.setdefault(p, {'param_name': p, 'unit': t(r['Ед.'])})
        vn = num(v)
        specs.append({'item_sname': s, 'param_name': p, 'value_num': vn, 'value_text': None if vn is not None else v,
                      'confidence': t(r['Достоверность']), 'source_code': sc, 'note': t(r['Примечание'])})
    C['param'], C['item_spec'] = list(params.values()), specs

    # ---- экипаж и возимый БК: разбор текстовых ячеек «Карточек техники»
    crew, ammo = [], []
    for r in b2['Карточки техники']:
        v = t(r['ВВТ'])
        for m in re.finditer(r'\s*(.+?) ×(\d+) \((экипаж|десант)\)(?:;|$)', r['Экипаж по ролям'] or ''):
            crew.append({'vehicle_sname': v, 'role_name': m.group(1).strip(), 'qty': int(m.group(2)), 'seat': m.group(3)})
        for m in re.finditer(r'\s*(.+?) — (\d+) шт\. \[([ABC])\](?:;|$)', r['Возимый БК'] or ''):
            a = t(m.group(1))
            if a not in items:
                log.add('vehicle_ammo_load', 'error', f2, 'Карточки техники', r['_row'], f'боеприпас «{a}» нет в каталоге'); continue
            ammo.append({'vehicle_sname': v, 'ammo_sname': a, 'qty': int(m.group(2)), 'confidence': m.group(3)})
        if r['Возимый БК'] and not any(x['vehicle_sname'] == v for x in ammo):
            log.add('vehicle_ammo_load', 'error', f2, 'Карточки техники', r['_row'], 'не удалось разобрать «Возимый БК»', r)
    C['vehicle_crew_role'], C['vehicle_ammo_load'] = crew, ammo

    # ---- собственное ВВТ: свои — «ВВТ по уровням» (v1, все позиции, все уровни); США — «Техника по подразделениям» (v2, ≤ взвода)
    def own_from_rollup(rows, codecol, itemcol, qtycol, sheet, fname, scope):
        totq = {}
        for r in rows:
            c, s = code(r[codecol]), t(r[itemcol])
            if not scope(c):
                continue
            if c not in units:
                log.add('holding', 'error', fname, sheet, r['_row'], f'подразделение {c} нет в структуре', r); continue
            if s not in items:
                log.add('holding', 'error', fname, sheet, r['_row'], f'«{s}» нет в каталоге', r); continue
            totq[(c, s)] = to_int(r[qtycol])
        own = []
        for (c, s), q in totq.items():
            sub = sum(totq.get((k, s), 0) for k in kids[c])
            o = q - sub
            if o < 0:
                log.add('holding', 'error', fname, sheet, None, f'{c} {s}: итог {q} меньше суммы подчинённых {sub}'); continue
            if o or (q == 0 and sub == 0):   # явный ноль в источнике тоже факт (позиция числится, но 0)
                own.append({'unit_code': c, 'item_sname': s, 'qty': o, 'derived_from': f'{sheet}: итог − подчинённые'})
        return own
    hold = own_from_rollup(b1['ВВТ по уровням'], 'Код', 'ВВТ', 'Кол-во', 'ВВТ по уровням', f1, lambda c: c.startswith('20.'))
    hold += own_from_rollup(b2['Техника по подразделениям'], 'Код', 'ВВТ', 'Кол-во', 'Техника по подразделениям', f2, lambda c: c.startswith('34.'))
    deep = sum(1 for u in units.values() if u['country'] == 'США' and u['unit_code'].count('.') > 10)
    if deep:
        log.add('holding', 'info', f2, 'Техника по подразделениям', None,
                f'лист выгружен до глубины 10: техника {deep} подразделений США глубже отнесена к их вышестоящим')
    C['holding'] = hold

    # ---- посадка: сопоставление со штатом по (код, должность, звание, ФИО-кратко), с учётом повторов
    slots = defaultdict(deque)
    for s in staff:
        short = ' '.join(x for x in (s['last_name'], s['first_name']) if x) or None
        slots[(s['unit_code'], s['position_name'], s['rank_name'], short)].append(s['staff_id'])
    ca = []
    for r in b2['Посадка экипажей']:
        key = (code(r['Код']), t(r['Должность']), t(r['Звание']), t(r['ФИО']))
        q = slots.get(key)
        if not q:
            log.add('crew_assignment', 'error', f2, 'Посадка экипажей', r['_row'], 'не найдено штатное место для посадки', r); continue
        veh = t(r['Машина'])
        if veh not in items:
            log.add('crew_assignment', 'error', f2, 'Посадка экипажей', r['_row'], f'машина «{veh}» нет в каталоге', r); continue
        ca.append({'staff_id': q.popleft(), 'vehicle_sname': veh, 'vehicle_no': to_int(r['№ машины']), 'seat': t(r['Место'])})
    C['crew_assignment'] = ca

    # ---- страны
    countries, milex = {}, []
    for r in b2['SIPRI расходы (ряд)']:
        ce = t(r['Country'])
        countries.setdefault(ce, {'country_en': ce, 'country_ru': t(r['Страна'])})
        milex.append({'country_en': ce, 'year': to_int(r['Год']), 'milex_usd_2019': num(r['Расходы, $ 2019']),
                      'share_gdp_pct': num(r['% ВВП']), 'per_capita_usd': num(r['$ на душу'])})
    forces = []
    for r in b2['Страны (профиль)']:
        ce = t(r['Country'])
        countries.setdefault(ce, {'country_en': ce, 'country_ru': t(r['Страна'])})
        if r['Численность ВС'] is not None or r['COW, тыс. (посл.)'] is not None:
            forces.append({'country_en': ce, 'af_year': to_int(r['Год (ВС)']), 'armed_forces_personnel': num(r['Численность ВС']),
                           'cow_milper_thousands': num(r['COW, тыс. (посл.)'])})
    C['country'], C['milex'], C['country_forces'] = list(countries.values()), milex, forces

    # что из листов не грузится как факты
    derived = {(f1, 'Численность'): 'сводный — сверка', (f1, 'Потребность по уровням'): 'сводный — сверка', (f1, 'ВВТ по уровням'): 'источник собственного ВВТ (итог − подчинённые) + сверка',
               (f1, 'Противник'): 'подмножество «Структура (все)» — сверка', (f1, 'Структура'): 'подмножество «Структура (все)»; берём только «Сторона»',
               (f1, 'Штат и л_с'): 'подмножество «Штат (все)»; берём ID людей', (f1, 'Табель по должностям'): 'подмножество v2', (f1, 'Комплекты'): 'подмножество v2',
               (f2, 'Структура (все)'): 'подразделения; численность пересчитана в собственную', (f2, 'Горючее (заправка)'): 'сводный — сверка',
               (f2, 'Боекомплект (всего)'): 'сводный — сверка', (f2, 'Техника по подразделениям'): 'источник собственного ВВТ для США + сверка',
               (f2, 'Сверка с источниками'): 'отчёт — не грузится', (f2, 'Расхождения источников'): 'производный от ТТХ — не грузится',
               (f2, 'Словарь данных'): 'описание объектов исходной БД — не грузится', (f2, 'Страны (профиль)'): 'берём только численность ВС (нет в других листах)'}
    return {'f1': f1, 'f2': f2, 'b1': b1, 'b2': b2}, C, log.rows, derived


# ============================================================== сверка с Excel после загрузки
def reconcile(cur, books, units):
    f1, f2, b1, b2 = books['f1'], books['f2'], books['b1'], books['b2']
    res, diffs = [], []

    def cmp(name, sheet, excel, db, note=''):
        keys = set(excel) | set(db)
        eq = sum(1 for k in keys if k in excel and k in db and excel[k] == db[k])
        oe = sum(1 for k in keys if k not in db)
        od = sum(1 for k in keys if k not in excel)
        df = [k for k in keys if k in excel and k in db and excel[k] != db[k]]
        res.append({'check_name': name, 'excel_sheet': sheet, 'rows_compared': len(keys), 'rows_equal': eq, 'rows_diff': len(df),
                    'only_in_excel': oe, 'only_in_db': od, 'note': note})
        for k in (df + [k for k in keys if k not in db or k not in excel])[:30]:
            diffs.append({'check': name, 'key': str(k), 'excel': excel.get(k), 'db': db.get(k)})

    def q(sql):
        cur.execute(sql); return cur.fetchall()

    cmp('Численность по категориям (свои)', f'{f1} / Численность',
        {code(r['Код']): (r['Всего'], r['Офицеры'], r['Прапорщики'], r['Сержанты'], r['Солдаты']) for r in b1['Численность']},
        {c: tuple(x) for c, *x in q("SELECT unit_code, staff_total, officers, warrant, sergeants, soldiers FROM mil_core.v_unit_staff_by_category WHERE unit_code LIKE '20.%'")})
    cmp('Численность с подчинёнными (все)', f'{f2} / Структура (все)',
        {code(r['Код']): (r['Л/с (с подчин.)'], r['Из них оценка']) for r in b2['Структура (все)']},
        {c: (a, b) for c, a, b in q('SELECT unit_code, personnel, personnel_estimated FROM mil_core.v_unit_personnel')})
    cmp('Штат = собственной численности (свои)', 'штат vs структура',
        {c: n for c, n in q("SELECT unit_code, personnel_own FROM mil_core.unit WHERE country='РФ' AND personnel_own > 0")},
        {c: n for c, n in q("SELECT unit_code, COUNT(*) FROM mil_core.staff_position WHERE unit_code LIKE '20.%' GROUP BY 1")},
        'независимая проверка: число штатных должностей в подразделении = его собственная численность')
    full2s = {i: s for s, i in q('SELECT item_sname, item_name FROM mil_core.item')}
    cmp('Потребность по табелю (свои)', f'{f1} / Потребность по уровням',
        {(code(r['Код']), full2s.get(t(r['Предмет']))): r['Кол-во'] for r in b1['Потребность по уровням']},
        {(c, s): int(n) for c, s, n in q("SELECT unit_code, item_sname, qty FROM mil_core.v_unit_need WHERE unit_code LIKE '20.%'")},
        'пересчёт штат × табель × комплекты')
    cmp('ВВТ с подчинёнными (свои)', f'{f1} / ВВТ по уровням',
        {(code(r['Код']), t(r['ВВТ'])): r['Кол-во'] for r in b1['ВВТ по уровням']},
        {(c, s): int(n) for c, s, n in q("SELECT unit_code, item_sname, qty FROM mil_core.v_unit_holding WHERE unit_code LIKE '20.%'")})
    cmp('Техника с подчинёнными (все, до взвода)', f'{f2} / Техника по подразделениям',
        {(code(r['Код']), t(r['ВВТ'])): r['Кол-во'] for r in b2['Техника по подразделениям']},
        {(c, s): int(n) for c, s, n in q("""SELECT h.unit_code, h.item_sname, h.qty FROM mil_core.v_unit_holding h JOIN mil_core.unit u USING (unit_code)
             JOIN mil_core.item i USING (item_sname) LEFT JOIN mil_core.v_item_fuel f USING (item_sname)
             WHERE u.depth <= 10 AND (i.category IN ('Бронетанковое вооружение и техника','Автомобильная техника и прицепы','Инженерная техника')
               OR (i.category='Ракетно-артиллерийское вооружение' AND EXISTS (SELECT 1 FROM mil_core.item_spec s WHERE s.item_sname=i.item_sname)) OR f.refill_l IS NOT NULL)""")},
        'кросс-проверка двух выгрузок (свои) и восстановления собственного ВВТ (США)')
    cmp('Горючее на одну заправку', f'{f2} / Горючее (заправка)',
        {(code(r['Код']), t(r['Вид топлива'])): (r['Ед. техники'], r['С данными'], round(float(r['Одна заправка, л'] or 0))) for r in b2['Горючее (заправка)']},
        {(c, ft): (int(v), int(w or 0), round(float(l))) for c, ft, v, w, l in q('SELECT f.unit_code, f.fuel_type, f.vehicles, f.vehicles_with_data, f.fuel_one_refill_l FROM mil_core.v_unit_fuel f JOIN mil_core.unit u USING (unit_code) WHERE u.depth <= 9')},
        'пересчёт техника × ТТХ')
    cmp('Боекомплект носимый + возимый', f'{f2} / Боекомплект (всего)',
        {(code(r['Код']), t(r['Боеприпас'])): (r['Носимый (л/с)'], r['Возимый (техника)']) for r in b2['Боекомплект (всего)']},
        {(c, a): (int(p), int(v)) for c, a, p, v in q('SELECT a.unit_code, a.ammo_sname, a.personal_load, a.vehicle_load FROM mil_core.v_unit_ammo a JOIN mil_core.unit u USING (unit_code) WHERE u.depth <= 9')},
        'пересчёт штат × табель + техника × возимый БК')
    cmp('Противник (омбр ПМИ)', f'{f1} / Противник',
        {code(r['Код']): r['Л/с'] for r in b1['Противник'] if code(r['Код']).startswith('34.0.0.1.')},
        {c: int(n) for c, n in q("SELECT unit_code, personnel FROM mil_core.v_unit_personnel WHERE unit_code LIKE '34.0.0.1.%'")},
        'узлы 34., 34.0., 34.0.0. не сравниваются: первая выгрузка сделана до добавления бригад США')
    return res, diffs


# ============================================================== загрузка
ORDER = ['source', 'unit_level', 'country', 'item', 'param', 'rank', 'position', 'kit', 'kit_item', 'position_kit', 'unit', 'person',
         'staff_position', 'item_spec', 'vehicle_crew_role', 'vehicle_ammo_load', 'holding', 'crew_assignment', 'milex', 'country_forces']


def load(dsn, src, books, C, rejects, init_schema, out):
    import psycopg2
    from psycopg2.extras import execute_values, Json
    con = psycopg2.connect(dsn)
    try:
        with con, con.cursor() as cur:
            if init_schema:
                cur.execute(open(init_schema, encoding='utf-8').read())
            cur.execute('INSERT INTO etl.load_run (source_dir) VALUES (%s) RETURNING run_id', (os.path.abspath(src),))
            run = cur.fetchone()[0]
            stage = []
            for fkey, bkey in (('f1', 'b1'), ('f2', 'b2')):
                for sheet, rows in books[bkey].items():
                    for r in rows:
                        stage.append((run, books[fkey], sheet, r['_row'], Json({k: (str(v) if v is not None else None) for k, v in r.items() if k != '_row'})))
            execute_values(cur, 'INSERT INTO excel_stage.raw_row VALUES %s', stage, page_size=5000)
            cur.execute('TRUNCATE ' + ', '.join(f'mil_core.{t}' for t in reversed(ORDER)) + ' RESTART IDENTITY')
            for ent in ORDER:
                rows = C[ent]
                if rows:
                    cols = list(rows[0].keys())
                    execute_values(cur, f'INSERT INTO mil_core.{ent} ({", ".join(cols)}) VALUES %s', [tuple(r[c] for c in cols) for r in rows], page_size=5000)
            cur.execute("SELECT setval('mil_core.staff_position_staff_id_seq', (SELECT max(staff_id) FROM mil_core.staff_position))")
            execute_values(cur, 'INSERT INTO etl.reject (run_id, entity, severity, src_file, src_sheet, src_row, reason, raw) VALUES %s',
                           [(run, r['entity'], r['severity'], r['src_file'], r['src_sheet'], r['src_row'], r['reason'], Json(r['raw'])) for r in rejects])
            rec, diffs = reconcile(cur, books, None)
            execute_values(cur, 'INSERT INTO etl.reconcile VALUES %s', [(run, r['check_name'], r['excel_sheet'], r['rows_compared'], r['rows_equal'],
                           r['rows_diff'], r['only_in_excel'], r['only_in_db'], r['note']) for r in rec])
            stats = {'loaded': {k: len(v) for k, v in C.items()}, 'rejects': dict(Counter(f"{r['entity']}:{r['severity']}" for r in rejects)),
                     'reconcile_all_equal': all(r['rows_diff'] == 0 and r['only_in_excel'] == 0 and r['only_in_db'] == 0 for r in rec)}
            cur.execute("UPDATE etl.load_run SET finished_at=clock_timestamp(), status='ok', stats=%s WHERE run_id=%s", (Json(stats), run))
        pd.DataFrame(rec).to_csv(os.path.join(out, 'reconcile.csv'), index=False, encoding='utf-8-sig')
        pd.DataFrame(diffs).to_csv(os.path.join(out, 'reconcile_diffs.csv'), index=False, encoding='utf-8-sig')
        return run, rec
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--src', required=True); ap.add_argument('--out', default='out')
    ap.add_argument('--dsn', default=os.environ.get('PG_DSN')); ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--init-schema')
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, 'clean'), exist_ok=True)
    books, C, rejects, derived = build(a.src)
    for ent, rows in C.items():
        pd.DataFrame(rows).to_csv(os.path.join(a.out, 'clean', f'{ent}.csv'), index=False, encoding='utf-8-sig')
    pd.DataFrame(rejects).assign(raw=lambda d: d['raw'].map(lambda x: json.dumps(x, ensure_ascii=False))) \
        .to_csv(os.path.join(a.out, 'rejects.csv'), index=False, encoding='utf-8-sig')
    pd.DataFrame([{'файл': f, 'лист': s, 'как используется': v} for (f, s), v in derived.items()]) \
        .to_csv(os.path.join(a.out, 'sheet_usage.csv'), index=False, encoding='utf-8-sig')
    print('чистых строк:', {k: len(v) for k, v in C.items()})
    print('журнал:', dict(Counter(f"{r['entity']}:{r['severity']}" for r in rejects)))
    if a.dry_run:
        return
    if not a.dsn:
        sys.exit('нужен --dsn / PG_DSN или --dry-run')
    run, rec = load(a.dsn, a.src, books, C, rejects, a.init_schema, a.out)
    print('run_id', run)
    print(pd.DataFrame(rec)[['check_name', 'rows_compared', 'rows_equal', 'rows_diff', 'only_in_excel', 'only_in_db']].to_string())


if __name__ == '__main__':
    main()
