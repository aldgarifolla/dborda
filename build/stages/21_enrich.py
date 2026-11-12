"""Заполняет расширение mil_core выдуманными данными (люди, выдача, техника, склады, нормы, заявки).
Запуск: python enrich.py "postgresql://..."   (после schema_enrich.sql; затем functions.sql)"""
import sys, random, math, datetime as dt
from collections import defaultdict
import psycopg2
from psycopg2.extras import execute_values

random.seed(2026)
TODAY = dt.date(2026, 10, 29)
con = psycopg2.connect(sys.argv[1]); cur = con.cursor()


def q(sql, a=None):
    cur.execute(sql, a); return cur.fetchall()


def ins(table, cols, rows, page=5000):
    if rows:
        execute_values(cur, f'INSERT INTO mil_core.{table} ({", ".join(cols)}) VALUES %s', rows, page_size=page)


def d(start, end):
    return start + dt.timedelta(days=random.randint(0, max((end - start).days, 0)))


def wchoice(pairs):
    v, w = zip(*pairs); return random.choices(v, w)[0]


# ============================================================ 1. новые позиции каталога
NEW = [('ДТ', 'Дизельное топливо ДТ (летнее/зимнее)', 'Горючее и смазочные материалы', 'л'),
       ('АИ-92', 'Бензин автомобильный АИ-92', 'Горючее и смазочные материалы', 'л'),
       ('JP-8', 'Авиакеросин JP-8 (единое топливо армии США)', 'Горючее и смазочные материалы', 'л'),
       ('М-10ДМ', 'Масло моторное М-10ДМ', 'Горючее и смазочные материалы', 'л'),
       ('ТАп-15В', 'Масло трансмиссионное ТАп-15В', 'Горючее и смазочные материалы', 'л'),
       ('ОЖ-40', 'Охлаждающая жидкость ОЖ-40', 'Горючее и смазочные материалы', 'л'),
       ('ИРП-Б', 'Индивидуальный рацион питания ИРП-Б (сутки на 1 человека)', 'Продовольствие', 'компл.'),
       ('Сутодача котловая', 'Продовольствие котлового довольствия (сутодача на 1 человека)', 'Продовольствие', 'сутодача'),
       ('Вода питьевая', 'Вода питьевая', 'Продовольствие', 'л'),
       ('MRE', 'Meal, Ready-to-Eat (сутки на 1 человека, США)', 'Продовольствие', 'компл.'),
       ('Аптечка войсковая', 'Аптечка войсковая (групповая) на взвод', 'Средства индивидуальной защиты и медицинское имущество', 'шт.'),
       ('Шина лестничная', 'Шина транспортная лестничная', 'Средства индивидуальной защиты и медицинское имущество', 'шт.'),
       ('Комплект санинструктора', 'Комплект санитарного инструктора роты', 'Средства индивидуальной защиты и медицинское имущество', 'компл.'),
       ('Комплект МП батальона', 'Комплект медицинского пункта батальона', 'Средства индивидуальной защиты и медицинское имущество', 'компл.'),
       ('Перевязочный материал', 'Перевязочный материал (комплект на 10 перевязок)', 'Средства индивидуальной защиты и медицинское имущество', 'компл.'),
       ('Кровезаменитель', 'Кровезаменитель, флакон 400 мл', 'Средства индивидуальной защиты и медицинское имущество', 'шт.'),
       ('Палатка ПЛ', 'Палатка лагерная на отделение', 'Ремонтные и тыловые средства', 'шт.'),
       ('Палатка УСБ-56', 'Палатка унифицированная санитарно-барачная УСБ-56', 'Ремонтные и тыловые средства', 'шт.'),
       ('Печь ПВ-1', 'Печь полевая ПВ-1', 'Ремонтные и тыловые средства', 'шт.'),
       ('Канистра 20 л', 'Канистра металлическая 20 л', 'Ремонтные и тыловые средства', 'шт.')]
have = {r[0] for r in q('SELECT item_sname FROM mil_core.item')}
ins('item', ['item_sname', 'item_name', 'category', 'country', 'unit_measure'],
    [(s, n, c, 'США' if 'США' in n or s == 'JP-8' else 'СССР/РФ', u) for s, n, c, u in NEW if s not in have])

# расход топлива (условный, для расчёта марша)
CONS = {'Т-72Б': 400, 'Т-72К': 400, 'БМП-2': 100, 'БМП-1К': 95, 'БМП-1КШ': 95, 'БРМ-1К': 95, 'БТР-80': 45, 'БТР-80ПБКМ': 45,
        'БРДМ-2': 30, 'БРДМ-2РХ': 30, 'МТ-ЛБ': 60, 'МТ-ЛБУ': 60, 'БМ 9А34': 60, '122-мм 2С1 Гвоздика': 80, 'БМ-21 РСЗО Град': 50,
        '23-мм ЗСУ-23-4 Шилка': 90, 'УРАЛ-4320': 35, 'КамАЗ-4310': 35, 'ЗИЛ-131': 40, 'ГАЗ-66Б': 28, 'УАЗ-3151': 17, 'УАЗ-452': 18,
        'УАЗ-452А': 18, 'АТМЗ-5-4320': 38, 'АЦ-8.5-255Б': 45, 'ТЗ-8-255Б': 45, 'БРЭМ-1': 420, 'M1A2 Abrams': 400, 'M2A3 Bradley': 190,
        'M109A6 Paladin': 160, 'M992A2 FAASV': 160, 'M113A3': 70, 'M577A3': 70, 'M1126 Stryker ICV': 45, 'M1165A1 HMMWV': 20,
        'JLTV M1278': 25, 'M1078A1 LMTV': 30, 'M1083 MTV': 33, 'M1074A1 PLS': 55, 'M88A2 Hercules': 350}
cur.execute("INSERT INTO mil_core.param VALUES ('Расход топлива на 100 км (условно)', 'л') ON CONFLICT DO NOTHING")
ins('item_spec', ['item_sname', 'param_name', 'value_num', 'confidence', 'source_code', 'note'],
    [(s, 'Расход топлива на 100 км (условно)', v, 'C', 'REF', 'условная норма для расчёта марша') for s, v in CONS.items()])

# синонимы для поиска предметов ассистентом
ALIAS = [('бензин', 'АИ-92'), ('аи92', 'АИ-92'), ('дизель', 'ДТ'), ('солярка', 'ДТ'), ('дизтопливо', 'ДТ'), ('керосин', 'JP-8'),
         ('масло моторное', 'М-10ДМ'), ('сухпай', 'ИРП-Б'), ('сухой паёк', 'ИРП-Б'), ('вода', 'Вода питьевая'), ('берцы', 'Ботинки с высокими берцами'),
         ('бронежилет', 'Бронежилет 6Б45'), ('каска', 'Шлем 6Б47'), ('шлем', 'Шлем 6Б47'), ('противогаз', 'Противогаз ПМК-2'), ('аптечка', 'Аптечка АИ-4'),
         ('автомат', '5,45-мм АК-74М'), ('ак', '5,45-мм АК-74М'), ('ак-74м', '5,45-мм АК-74М'), ('пистолет', '9-мм ПМ'), ('пм', '9-мм ПМ'),
         ('патроны 5.45', '5.45-мм ПС (7Н6)'), ('патроны 5,45', '5.45-мм ПС (7Н6)'), ('патроны к автомату', '5.45-мм ПС (7Н6)'),
         ('патроны 9мм', '9-мм П (57-Н-181)'), ('патроны пкт', '7.62-мм ЛПС (57-Н-323С)'), ('граната', 'Ф-1'), ('рпг', 'РПГ-7Д'),
         ('бмп', 'БМП-2'), ('танк', 'Т-72Б'), ('бензовоз', 'АТМЗ-5-4320'), ('топливозаправщик', 'АТМЗ-5-4320'), ('рация', 'Р-168-0,5У')]
cur.execute('CREATE TABLE mil_core.item_alias (alias TEXT PRIMARY KEY, item_sname TEXT NOT NULL REFERENCES mil_core.item)')
ins('item_alias', ['alias', 'item_sname'], ALIAS)

# ============================================================ 2. люди: американцы без людей получают вымышленные ФИО
US_FIRST = ['James', 'Michael', 'Robert', 'John', 'David', 'William', 'Richard', 'Joseph', 'Thomas', 'Christopher', 'Daniel', 'Matthew',
            'Anthony', 'Mark', 'Steven', 'Andrew', 'Joshua', 'Kevin', 'Brian', 'Ryan', 'Jacob', 'Tyler', 'Brandon', 'Justin', 'Carlos',
            'Luis', 'Jose', 'Marcus', 'Andre', 'Ashley', 'Jessica', 'Emily', 'Sarah', 'Maria']
US_LAST = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez',
           'Gonzalez', 'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson', 'White',
           'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson', 'Walker', 'Young', 'Allen', 'King', 'Wright', 'Scott', 'Nguyen',
           'Hill', 'Flores', 'Green', 'Adams', 'Nelson', 'Baker', 'Hall', 'Rivera', 'Campbell', 'Mitchell', 'Carter', 'Roberts']
FEMALE_US = {'Ashley', 'Jessica', 'Emily', 'Sarah', 'Maria'}
free = q('''SELECT s.staff_id FROM mil_core.staff_position s JOIN mil_core.unit u USING (unit_code) WHERE s.person_id IS NULL ORDER BY staff_id''')
next_id = q('SELECT max(person_id) FROM mil_core.person')[0][0] + 1
new_people, links = [], []
for (sid,) in free:
    fn = random.choice(US_FIRST)
    new_people.append((next_id, random.choice(US_LAST), fn, random.choice('ABCDEFGHJKLMNPRSTW') + '.'))
    links.append((next_id, sid)); next_id += 1
ins('person', ['person_id', 'last_name', 'first_name', 'patronymic'], new_people)
execute_values(cur, 'UPDATE mil_core.staff_position s SET person_id = v.pid FROM (VALUES %s) v(pid, sid) WHERE s.staff_id = v.sid', links)

# ============================================================ 3. личные карточки
people = q('''SELECT p.person_id, p.first_name, s.rank_name, r.category, r.army, s.position_name, u.unit_code
              FROM mil_core.person p JOIN mil_core.staff_position s USING (person_id) JOIN mil_core.rank r USING (rank_name)
              JOIN mil_core.unit u USING (unit_code)''')
AGE_RU = {'рядовой': (18, 30), 'ефрейтор': (19, 32), 'младший сержант': (20, 33), 'сержант': (21, 36), 'старший сержант': (23, 40),
          'старшина': (25, 45), 'прапорщик': (24, 45), 'старший прапорщик': (30, 50), 'лейтенант': (21, 26), 'старший лейтенант': (23, 29),
          'капитан': (25, 35), 'майор': (29, 42), 'подполковник': (33, 46), 'полковник': (38, 52)}
AGE_US = {'PVT': (18, 23), 'PFC': (18, 25), 'SPC': (19, 28), 'SGT': (21, 32), 'SSG': (24, 35), 'SFC': (28, 40), '1SG': (32, 44),
          '2LT': (21, 25), '1LT': (23, 28), 'CPT': (26, 34), 'MAJ': (31, 40), 'LTC': (36, 45), 'COL': (40, 50)}
NAT_RU = [('русский', 78), ('татарин', 4), ('украинец', 2.5), ('башкир', 2), ('чуваш', 1.5), ('белорус', 1.5), ('казах', 1.5),
          ('мордвин', 1), ('удмурт', 1), ('бурят', 1), ('якут', 0.8), ('аварец', 0.8), ('осетин', 0.8), ('армянин', 0.8), ('чеченец', 0.7), ('марийец', 0.6)]
REG_RU = ['Москва', 'Московская обл.', 'Санкт-Петербург', 'Свердловская обл.', 'Челябинская обл.', 'Новосибирская обл.', 'Омская обл.',
          'Самарская обл.', 'Нижегородская обл.', 'Ростовская обл.', 'Краснодарский край', 'Воронежская обл.', 'Саратовская обл.',
          'Пермский край', 'Тюменская обл.', 'Красноярский край', 'Алтайский край', 'Иркутская обл.', 'Оренбургская обл.', 'Волгоградская обл.']
NAT_REG = {'татарин': 'Республика Татарстан', 'башкир': 'Республика Башкортостан', 'чуваш': 'Чувашская Республика', 'мордвин': 'Республика Мордовия',
           'удмурт': 'Удмуртская Республика', 'бурят': 'Республика Бурятия', 'якут': 'Республика Саха (Якутия)', 'аварец': 'Республика Дагестан',
           'осетин': 'Республика Северная Осетия', 'чеченец': 'Чеченская Республика', 'марийец': 'Республика Марий Эл'}
US_STATES = ['Texas', 'California', 'Florida', 'Georgia', 'North Carolina', 'Ohio', 'Pennsylvania', 'New York', 'Virginia', 'Tennessee',
             'Alabama', 'Arizona', 'Michigan', 'Kentucky', 'Oklahoma', 'Colorado', 'Washington', 'Missouri', 'South Carolina', 'Illinois']
BLOOD = [('0(I) Rh+', 32), ('A(II) Rh+', 33), ('B(III) Rh+', 18), ('AB(IV) Rh+', 6), ('0(I) Rh−', 5), ('A(II) Rh−', 4), ('B(III) Rh−', 1.5), ('AB(IV) Rh−', 0.5)]
VACC = ['Столбняк, дифтерия (АДС-М)', 'Грипп (сезонная)', 'Гепатит B', 'Корь', 'Менингококковая инфекция', 'Клещевой энцефалит']

profiles, vacc, sizes = [], [], {}
for pid, first, rank, cat, army, pos, ucode in people:
    us = army == 'США'
    short = rank.split('(')[-1].rstrip(')') if us else rank
    lo, hi = (AGE_US if us else AGE_RU).get(short, (20, 35))
    age = random.randint(lo, hi)
    bdate = TODAY.replace(year=TODAY.year - age) - dt.timedelta(days=random.randint(1, 364))
    sex = 'Ж' if us and first in FEMALE_US else 'М'
    h = round(random.gauss(177 if sex == 'М' else 165, 6.5))
    h = max(158, min(200, h))
    bmi = max(18.5, min(31, random.gauss(23.6 + (age - 25) * 0.08, 2.4)))
    w = round(bmi * (h / 100) ** 2)
    chest = max(82, min(124, round(88 + (bmi - 22) * 3.2 + (h - 176) * 0.15 + random.gauss(0, 2.5))))
    head = max(53, min(63, round(random.gauss(57.5, 1.4))))
    if us:
        cs = 'XS' if chest < 86 else 'S' if chest < 92 else 'M' if chest < 100 else 'L' if chest < 108 else 'XL' if chest < 116 else 'XXL'
        clothing = f"{cs}-{'Short' if h < 170 else 'Regular' if h < 185 else 'Long'}"
        shoe = str(max(6, min(14, round((h - 150) / 5 + random.gauss(0, 0.6)))))
        helmet = 'S' if head < 55 else 'M' if head < 58 else 'L' if head < 60 else 'XL'
        nat, birthplace = 'американец' if sex == 'М' else 'американка', random.choice(US_STATES)
        stype, start = 'по контракту', d(TODAY - dt.timedelta(days=365 * max(1, age - 18)), TODAY - dt.timedelta(days=120))
        cend = start + dt.timedelta(days=365 * random.choice([3, 4, 6]))
        edu = 'бакалавр' if cat == 'офицеры' else random.choice(['High School', 'High School', 'Some College', 'Associate degree'])
    else:
        sz = max(44, min(62, int(round(chest / 4)) * 2))
        grp = max(1, min(6, round((h - 158) / 6) + 1))
        clothing = f'{sz}-{grp}'
        shoe = str(max(38, min(47, round(38 + (h - 160) / 5.5 + random.gauss(0, 0.7)))))
        helmet = '1' if head <= 56 else '2' if head <= 59 else '3'
        nat = wchoice(NAT_RU)
        birthplace = NAT_REG.get(nat) or random.choice(REG_RU)
        if cat in ('офицеры', 'прапорщики') or (cat == 'сержанты' and random.random() < 0.85) or random.random() < 0.45:
            stype = 'по контракту'
            start = d(TODAY - dt.timedelta(days=365 * max(1, min(age - 18, 25))), TODAY - dt.timedelta(days=60))
            cend = start + dt.timedelta(days=365 * random.choice([1, 2, 3, 5]))
            while cend < TODAY:
                cend += dt.timedelta(days=365 * 3)
        else:
            stype, start, cend = 'по призыву', d(TODAY - dt.timedelta(days=360), TODAY - dt.timedelta(days=20)), None
        edu = ('высшее военное' if cat == 'офицеры' else 'среднее профессиональное' if cat == 'прапорщики'
               else random.choice(['среднее общее', 'среднее общее', 'среднее профессиональное', 'высшее']))
    glove = str(max(7, min(11, round(8 + (h - 165) / 12))))
    married = random.random() < (0.15 + min(age - 18, 20) * 0.035)
    profiles.append((pid, (f'US-{random.randint(10**9, 10**10 - 1)}' if us else f'ЛН-{pid:06d}'), bdate, sex, nat, birthplace, h, w, chest, head,
                     clothing, shoe, str(head), helmet, glove, wchoice(BLOOD),
                     wchoice([('А', 70), ('Б-3', 25), ('Б-4', 5)]), stype, start, cend, edu,
                     ('женат' if sex == 'М' else 'замужем') if married else ('холост' if sex == 'М' else 'не замужем'),
                     (random.choice([0, 1, 1, 2, 2, 3]) if married else 0),
                     'нет' if random.random() < 0.94 else random.choice(['пенициллин', 'пыльца растений', 'цитрусовые', 'новокаин', 'пчелиный яд']),
                     d(TODAY - dt.timedelta(days=330), TODAY - dt.timedelta(days=5))))
    for v in random.sample(VACC, random.randint(3, 5)):
        vacc.append((pid, v, d(start - dt.timedelta(days=30), TODAY - dt.timedelta(days=3))))
    sizes[pid] = dict(clothing=clothing, shoe=shoe, head=str(head), helmet=helmet, glove=glove, h=h, chest=chest, us=us, start=start)
ins('person_profile', ['person_id', 'personal_number', 'birth_date', 'sex', 'nationality', 'birthplace', 'height_cm', 'weight_kg', 'chest_cm',
                       'head_cm', 'clothing_size', 'shoe_size', 'head_size', 'helmet_size', 'glove_size', 'blood_group', 'fitness_category',
                       'service_type', 'service_start', 'contract_end', 'education', 'marital_status', 'children', 'allergies', 'last_med_exam'], profiles)
ins('person_vaccination', ['person_id', 'vaccine', 'vaccinated_on'], vacc)

# ============================================================ 4. выдача имущества по табелю, с размерами и номерами
SIZE_BY = {'Костюм летний полевой': 'clothing', 'Костюм зимний полевой': 'clothing', 'Куртка ветровлагозащитная': 'clothing',
           'Бельё нательное': 'clothing', 'Футболка': 'clothing', 'Комбинезон танковый': 'clothing', 'Комбинезон технический': 'clothing',
           'Ботинки с высокими берцами': 'shoe', 'Носки': 'shoe', 'Кепи полевое': 'head', 'Шапка вязаная': 'head', 'Перчатки полевые': 'glove',
           'Шлем 6Б47': 'helmet', 'Шлемофон ТШ-5': 'helmet', 'Противогаз ПМК-2': 'helmet', 'Бронежилет 6Б45': 'vest', 'ОЗК': 'ozk',
           'Форма OCP': 'clothing', 'Ботинки боевые (США)': 'shoe', 'Шлем ACH/IHPS': 'helmet', 'Шлем танкиста CVC': 'helmet', 'Бронежилет IOTV': 'vest'}
WEAR_DAYS = {'Костюм летний полевой': 365, 'Костюм зимний полевой': 730, 'Куртка ветровлагозащитная': 730, 'Бельё нательное': 365,
             'Футболка': 180, 'Носки': 180, 'Ботинки с высокими берцами': 365, 'Кепи полевое': 365, 'Шапка вязаная': 730,
             'Перчатки полевые': 365, 'Форма OCP': 365, 'Ботинки боевые (США)': 365}
SERIAL_PREFIX = {'5,45-мм  АК-74М': 'АК', '5,45-мм АК-74М': 'АК', '5,45-мм АКС-74У': 'АУ', '9-мм ПМ': 'ПМ', '5,45-мм РПК-74': 'РП', '7,62-мм ПКМ': 'ПК',
                 '7,62-мм СВД': 'СВ', 'РПГ-7Д': 'РГ', '40-мм ГП-25': 'ГП', 'Р-168-0,5У': 'РС', 'Р-159': 'Р1', 'ПНВ 1ПН138': 'НВ',
                 'ПСО-1': 'ПО', 'ПГО-7': 'ПГ', 'Бинокль Б-8': 'БН', 'Миноискатель ИМП-2': 'МИ', 'ДП-5В': 'ДП',
                 '5,56-мм M4A1': 'W', '9-мм M17': 'P', '5,56-мм M249': 'S', '7,62-мм M240B': 'G', '40-мм M320': 'L',
                 'ПТРК FGM-148 Javelin': 'JV', 'AN/PRC-152': 'RD', 'ПНВ AN/PVS-14': 'NV'}


def size_for(item, s):
    kind = SIZE_BY.get(item)
    if not kind:
        return None
    if kind == 'vest':
        return ('S' if s['chest'] < 92 else 'M' if s['chest'] < 102 else 'L' if s['chest'] < 112 else 'XL') if s['us'] else \
               ('1' if s['chest'] < 92 else '2' if s['chest'] < 100 else '3' if s['chest'] < 108 else '4')
    if kind == 'ozk':
        return '1' if s['h'] < 166 else '2' if s['h'] < 172 else '3' if s['h'] < 178 else '4' if s['h'] < 186 else '5'
    return s[kind]


norms = defaultdict(list)
for pos, sname, qty, kit in q('SELECT pk.position_name, ki.item_sname, ki.qty, pk.kit_code FROM mil_core.position_kit pk JOIN mil_core.kit_item ki USING (kit_code)'):
    norms[pos].append((sname, qty, kit))
person_pos = q('SELECT person_id, position_name FROM mil_core.staff_position WHERE person_id IS NOT NULL')
issues, serial_seq = [], defaultdict(int)
for pid, pos in person_pos:
    s = sizes[pid]
    issued = d(s['start'], min(s['start'] + dt.timedelta(days=10), TODAY))
    agg = defaultdict(lambda: [0, None])
    for sname, qty, kit in norms.get(pos, []):
        agg[sname][0] += qty; agg[sname][1] = agg[sname][1] or kit
    for sname, (qty, kit) in agg.items():
        wear = issued + dt.timedelta(days=WEAR_DAYS[sname]) if sname in WEAR_DAYS else None
        pref = SERIAL_PREFIX.get(sname)
        if pref:
            for _ in range(qty):
                serial_seq[pref] += 1
                yr = random.randint(1988, 2019) if not s['us'] else random.randint(2005, 2022)
                issues.append((pid, sname, 1, None, f'{pref}{yr % 100:02d}{serial_seq[pref]:06d}', issued, None, kit))
        else:
            issues.append((pid, sname, qty, size_for(sname, s), None, issued, wear, kit))
ins('person_issue', ['person_id', 'item_sname', 'qty', 'size', 'serial_no', 'issued_on', 'wear_until', 'kit_code'], issues)

# ============================================================ 5. техника поштучно
VEH_CATS = ('Бронетанковое вооружение и техника', 'Автомобильная техника и прицепы', 'Инженерная техника')
spec = {}
for s, p, vn, vt in q('''SELECT item_sname, param_name, value_num, value_text FROM mil_core.item_spec ORDER BY confidence DESC'''):
    spec[(s, p)] = vn if vn is not None else vt
fuelmap = {}
for s, rf, ft in q('SELECT item_sname, refill_l, fuel_type FROM mil_core.v_item_fuel'):
    prod = None
    if ft:
        prod = 'JP-8' if 'JP-8' in ft else 'ДТ' if 'дизель' in ft else 'АИ-92' if 'бензин' in ft else None
    fuelmap[s] = (float(rf) if rf is not None else None, prod)
hold = q(f'''SELECT h.unit_code, h.item_sname, h.qty, u.country, u.unit_code FROM mil_core.holding h JOIN mil_core.item i USING (item_sname)
             JOIN mil_core.unit u USING (unit_code)
             WHERE h.qty > 0 AND (i.category IN %s OR EXISTS (SELECT 1 FROM mil_core.item_spec s WHERE s.item_sname = i.item_sname
                   AND s.param_name IN ('Экипаж (расчёт)', 'Вид топлива')))''', (VEH_CATS,))
CARGO = {'АТМЗ-5-4320': 5000, 'АЦ-8.5-255Б': 8500, 'ТЗ-8-255Б': 8000, 'M978A4 HEMTT': 9463}
vehicles, fno, item_idx, tac_seq = [], defaultdict(int), {}, defaultdict(int)
for ucode, sname, qty, country, _ in hold:
    rf, prod = fuelmap.get(sname, (None, None))
    if prod is None and country == 'РФ' and sname in CONS:
        prod = 'ДТ'
    seg = ucode.strip('.').split('.')
    for n in range(1, qty + 1):
        fno[sname] += 1
        item_idx.setdefault(sname, len(item_idx) + 1)
        st = wchoice([('исправна', 86), ('требует ТО', 8), ('требует ремонта', 4), ('в ремонте', 2)])
        lvl = round(rf * random.uniform(0.35, 1.0), 1) if rf else (0 if rf == 0 else None)
        if country == 'РФ' and len(seg) > 6:
            key = tuple(seg[6:9]); tac_seq[key] += 1
            tactical = ''.join(str(int(x) + 1) for x in seg[6:9]) + str(tac_seq[key])
        else:
            key = tuple(seg[4:7]); tac_seq[key] += 1
            tactical = '-'.join(str(int(x) + 1) for x in seg[4:7]) + f'-{tac_seq[key]}'
        cargo_p, cargo_l = (prod or 'ДТ', round(CARGO[sname] * random.uniform(0.2, 1.0))) if sname in CARGO else (None, None)
        if sname == 'АЦ-8.5-255Б' and n <= 3:
            cargo_p = 'АИ-92'
        yr = random.randint(1985, 2012) if country == 'РФ' else random.randint(2004, 2021)
        vehicles.append((sname, ucode, n, tactical, f'{"РФ" if country == "РФ" else "US"}-{item_idx[sname]:03d}-{fno[sname]:05d}', yr,
                         int(random.randint(2000, 45000) * (1 if sname not in ('Т-72Б', 'БМП-2', 'M1A2 Abrams', 'M2A3 Bradley') else 0.3)),
                         random.randint(150, 3500), st, prod, lvl, cargo_p, cargo_l))
ins('vehicle', ['item_sname', 'unit_code', 'vehicle_no', 'tactical_no', 'factory_no', 'year_made', 'mileage_km', 'motor_hours', 'status',
                'fuel_product', 'fuel_level_l', 'cargo_product', 'cargo_level_l'], vehicles)
cur.execute('''UPDATE mil_core.crew_assignment c SET vehicle_id = v.vehicle_id FROM mil_core.staff_position s, mil_core.vehicle v
               WHERE s.staff_id = c.staff_id AND v.unit_code = s.unit_code AND v.item_sname = c.vehicle_sname AND v.vehicle_no = c.vehicle_no''')

# ============================================================ 6. групповое имущество подразделений (условные нормы)
units = q('SELECT unit_code, short_name, level_name, country FROM mil_core.unit')
prop = []
for code, sn, lvl, country in units:
    if country != 'РФ':
        continue
    if sn.endswith('мсо') or (lvl == 'Отделение'):
        prop += [(code, 'Палатка ПЛ', 1, 'отделение'), (code, 'Канистра 20 л', 2, 'отделение')]
    elif lvl == 'Взвод':
        prop += [(code, 'Аптечка войсковая', 1, 'взвод'), (code, 'Шина лестничная', 4, 'взвод'), (code, 'Носилки', 2, 'взвод'),
                 (code, 'Перевязочный материал', 3, 'взвод')]
    elif lvl in ('Рота', 'Батарея'):
        prop += [(code, 'Комплект санинструктора', 1, 'рота/батарея'), (code, 'Палатка УСБ-56', 2, 'рота/батарея'),
                 (code, 'Печь ПВ-1', 2, 'рота/батарея'), (code, 'ТВН-12', 6, 'рота/батарея')]
    elif lvl in ('Батальон', 'Дивизион'):
        prop += [(code, 'Комплект МП батальона', 1, 'батальон/дивизион'), (code, 'Кровезаменитель', 20, 'батальон/дивизион')]
ins('unit_property', ['unit_code', 'item_sname', 'qty', 'basis'], prop)

# ============================================================ 7. склады
BDE, ARMY, ABCT = '20.0.6.0.0.2.', '20.0.6.0.', '34.0.0.2.'
cur.execute("""INSERT INTO mil_core.warehouse (warehouse_name, kind, unit_code, serves_unit_code, parent_warehouse_id, capacity_note) VALUES
  ('Окружной склад (вышестоящий, условно)', 'вышестоящий', '20.0.6.', '20.0.6.', NULL, 'резерв округа, все виды'),
  ('Склад армии (вышестоящий)', 'вышестоящий', %s, %s, 1, 'все виды имущества'),
  ('Склад ГСМ 12 мбр', 'ГСМ', '20.0.6.0.0.2.13.2.', %s, 2, 'резервуары 4 × 50 м³ + 2 × 25 м³ (условно)'),
  ('Склад РАВ (боеприпасы) 12 мбр', 'РАВ', '20.0.6.0.0.2.13.2.', %s, 2, NULL),
  ('Вещевой склад 12 мбр', 'вещевой', '20.0.6.0.0.2.13.2.', %s, 2, NULL),
  ('Продовольственный склад 12 мбр', 'продовольственный', '20.0.6.0.0.2.13.2.', %s, 2, NULL),
  ('Медицинский склад 12 мбр', 'медицинский', '20.0.6.0.0.2.13.3.', %s, 2, NULL),
  ('Theater sustainment (вышестоящий, США)', 'вышестоящий', '34.0.0.', '34.0.0.', NULL, 'условно'),
  ('ABCT BSB: Class III (ГСМ)', 'ГСМ', '34.0.0.2.7.1.', %s, 8, 'Distribution Co'),
  ('ABCT BSB: Class V (боеприпасы)', 'РАВ', '34.0.0.2.7.1.', %s, 8, 'Distribution Co'),
  ('ABCT BSB: Class I (продовольствие)', 'продовольственный', '34.0.0.2.7.1.', %s, 8, 'Distribution Co')""",
            (ARMY, ARMY, BDE, BDE, BDE, BDE, BDE, ABCT, ABCT, ABCT))
WH = {n: i for i, n in q('SELECT warehouse_id, warehouse_name FROM mil_core.warehouse')}

personnel = {c: int(n) for c, n in q("SELECT unit_code, personnel FROM mil_core.v_unit_personnel WHERE unit_code IN (%s, %s)", (BDE, ABCT))}
norm_rows = []


def norm(wh, item, qty, basis, size=''):
    if qty and qty > 0:
        norm_rows.append((WH[wh], item, size, round(qty, 1), basis))


# ГСМ: 1 заправка всей техники бригады
for prod, tot in q('''SELECT fuel_product, SUM(f.refill_l) FROM mil_core.vehicle v JOIN mil_core.v_item_fuel f USING (item_sname)
                      WHERE v.unit_code LIKE %s AND fuel_product IS NOT NULL GROUP BY 1''', (BDE + '%',)):
    norm('Склад ГСМ 12 мбр', prod, float(tot), '1 заправка всей техники бригады')
dt_norm = next(r[3] for r in norm_rows if r[1] == 'ДТ')
norm('Склад ГСМ 12 мбр', 'М-10ДМ', dt_norm * 0.03, '3 % от нормы ДТ')
norm('Склад ГСМ 12 мбр', 'ТАп-15В', dt_norm * 0.01, '1 % от нормы ДТ')
norm('Склад ГСМ 12 мбр', 'ОЖ-40', dt_norm * 0.005, '0,5 % от нормы ДТ')
for prod, tot in q('''SELECT fuel_product, SUM(f.refill_l) FROM mil_core.vehicle v JOIN mil_core.v_item_fuel f USING (item_sname)
                      WHERE v.unit_code LIKE %s AND fuel_product IS NOT NULL GROUP BY 1''', (ABCT + '%',)):
    norm('ABCT BSB: Class III (ГСМ)', prod, float(tot), '1 заправка всей техники ABCT')
# РАВ: 1 БК (носимый + возимый)
for a, tot in q('SELECT ammo_sname, total FROM mil_core.v_unit_ammo WHERE unit_code = %s', (BDE,)):
    norm('Склад РАВ (боеприпасы) 12 мбр', a, float(tot), '1 боекомплект бригады (носимый + возимый)')
for a, tot in q('SELECT ammo_sname, total FROM mil_core.v_unit_ammo WHERE unit_code = %s', (ABCT,)):
    norm('ABCT BSB: Class V (боеприпасы)', a, float(tot), '1 basic load ABCT (носимый + возимый)')
for s, n in q('''SELECT i.item_sname, COUNT(*) FROM mil_core.person_issue i JOIN mil_core.staff_position sp USING (person_id)
                 WHERE i.serial_no IS NOT NULL AND sp.unit_code LIKE %s AND i.item_sname IN
                 (SELECT item_sname FROM mil_core.item WHERE category = 'Стрелковое оружие и гранатомёты') GROUP BY 1''', (BDE + '%',)):
    norm('Склад РАВ (боеприпасы) 12 мбр', s, math.ceil(n * 0.03), 'резерв 3 % закреплённого оружия')
# вещевое: 10 % выданного по каждому размеру
for s, sz, n in q('''SELECT i.item_sname, COALESCE(i.size, ''), SUM(i.qty) FROM mil_core.person_issue i JOIN mil_core.staff_position sp USING (person_id)
                     JOIN mil_core.item it USING (item_sname) WHERE sp.unit_code LIKE %s AND it.category IN
                     ('Вещевое имущество', 'Средства индивидуальной бронезащиты и снаряжение') GROUP BY 1, 2''', (BDE + '%',)):
    norm('Вещевой склад 12 мбр', s, max(1, math.ceil(n * 0.1)), 'резерв 10 % выданного (по размеру)', sz)
# продовольствие
P = personnel[BDE]
norm('Продовольственный склад 12 мбр', 'ИРП-Б', P * 3, '3 суток × численность бригады')
norm('Продовольственный склад 12 мбр', 'Сутодача котловая', P * 7, '7 суток × численность бригады')
norm('Продовольственный склад 12 мбр', 'Вода питьевая', P * 5 * 3, '5 л в сутки × 3 суток × численность')
norm('ABCT BSB: Class I (продовольствие)', 'MRE', personnel[ABCT] * 3, '3 days × personnel')
norm('ABCT BSB: Class I (продовольствие)', 'Вода питьевая', personnel[ABCT] * 5 * 3, '5 л × 3 суток × численность')
# медицинское: 20 % индивидуальных средств + групповые
for s, n in q('''SELECT i.item_sname, SUM(i.qty) FROM mil_core.person_issue i JOIN mil_core.staff_position sp USING (person_id)
                 JOIN mil_core.item it USING (item_sname) WHERE sp.unit_code LIKE %s AND it.category = 'Средства индивидуальной защиты и медицинское имущество'
                 GROUP BY 1''', (BDE + '%',)):
    norm('Медицинский склад 12 мбр', s, math.ceil(n * 0.2), 'резерв 20 % индивидуальных средств')
for s, n in [('Кровезаменитель', 300), ('Перевязочный материал', 400), ('Шина лестничная', 80), ('Аптечка войсковая', 20)]:
    norm('Медицинский склад 12 мбр', s, n, 'запас медицинской роты (условно)')
ins('stock_norm', ['warehouse_id', 'item_sname', 'size', 'norm_qty', 'basis'], norm_rows)

# ============================================================ 8. остатки и движение
mv = []
START = dt.datetime(2026, 10, 1, 9, 0)
bn_units = [c for c, sn, lvl, ctry in units if ctry == 'РФ' and lvl in ('Батальон', 'Дивизион') and c.startswith(BDE)]
for wid, item, size, nq, basis in norm_rows:
    target = float(nq) * random.uniform(0.55, 1.2)
    if item == 'АИ-92' and wid == WH['Склад ГСМ 12 мбр']:
        target = 380.0                      # бензина на складе меньше нормы — для примера заявки
    if size == '46' and item == 'Ботинки с высокими берцами':
        target = 0.0
    unit = q('SELECT unit_measure FROM mil_core.item WHERE item_sname=%s', (item,))[0][0]
    integer = unit != 'л'
    receipts, issues_ = [], []
    if item in ('ДТ', 'АИ-92', 'JP-8', 'ИРП-Б', 'Сутодача котловая', 'Вода питьевая', 'MRE') or random.random() < 0.15:
        for _ in range(random.randint(1, 3)):
            receipts.append(float(nq) * random.uniform(0.1, 0.35))
        for _ in range(random.randint(2, 6)):
            issues_.append(float(nq) * random.uniform(0.03, 0.15))
    opening = target - sum(receipts) + sum(issues_)
    if opening < 0:
        receipts = []; opening = target + sum(issues_)
    r = (lambda x: float(round(x))) if integer else (lambda x: round(x, 1))
    if r(opening) > 0:
        mv.append((wid, item, size, r(opening), 'остаток на начало', START, None, 'опись 01.10.2026'))
    t = START
    for x in receipts:
        t += dt.timedelta(days=random.randint(1, 6), hours=random.randint(0, 8))
        mv.append((wid, item, size, r(x), 'приход', t, 'Склад армии (вышестоящий)', f'накл. № {random.randint(100, 999)}'))
    for x in issues_:
        t2 = START + dt.timedelta(days=random.randint(1, 27), hours=random.randint(0, 10))
        if r(x) > 0:
            mv.append((wid, item, size, -r(x), 'выдача', t2, random.choice(bn_units) if wid < 8 else '34.0.0.2.1.', f'треб. № {random.randint(1000, 9999)}'))
# вышестоящие склады: большие остатки по всему, что есть в нормах
for wid, item, size, nq, basis in norm_rows:
    up = WH['Склад армии (вышестоящий)'] if wid < 8 else WH['Theater sustainment (вышестоящий, США)']
    upq = float(round(float(nq) * random.uniform(2, 5)))
    if size:
        upq = max(upq, 40.0)          # на вышестоящем складе есть все размеры
    mv.append((up, item, size, upq, 'остаток на начало', START, None, 'опись 01.10.2026'))
have_up = {(m[1], m[2]) for m in mv if m[0] == WH['Склад армии (вышестоящий)']}
for sz in range(38, 48):
    for it in ('Ботинки с высокими берцами', 'Носки'):
        if (it, str(sz)) not in have_up:
            mv.append((WH['Склад армии (вышестоящий)'], it, str(sz), 40.0, 'остаток на начало', START, None, 'опись 01.10.2026'))
mv = [m for m in mv if m[3] != 0]
ins('stock_movement', ['warehouse_id', 'item_sname', 'size', 'qty', 'movement_type', 'moved_at', 'counterparty', 'doc_no'], mv)

# ============================================================ 9. примеры заявок
cur.execute("""INSERT INTO mil_core.supply_request (created_at, requester_unit, to_warehouse_id, item_sname, size, qty, status, reason, created_by) VALUES
 ('2026-10-20 10:15+05', '20.0.6.0.0.2.2.', %s, 'ДТ', '', 4000, 'выполнена', 'дозаправка техники после учений', 'пользователь'),
 ('2026-10-27 16:40+05', %s, %s, 'Ботинки с высокими берцами', '46', 12, 'создана', 'нет размера 46 на вещевом складе', 'пользователь')""",
            (WH['Склад ГСМ 12 мбр'], '20.0.6.0.0.2.13.2.', WH['Склад армии (вышестоящий)']))
con.commit()
for t in ['person', 'person_profile', 'person_vaccination', 'person_issue', 'vehicle', 'unit_property', 'warehouse', 'stock_norm', 'stock_movement', 'supply_request', 'item_alias']:
    print(t, q(f'SELECT count(*) FROM mil_core.{t}')[0][0])
print('crew linked', q('SELECT count(vehicle_id), count(*) FROM mil_core.crew_assignment')[0])
