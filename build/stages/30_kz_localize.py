# ВОССТАНОВЛЕННАЯ ВЕРСИЯ. Исходный файл: military_full (1).zip : military_full/src/kz_localize.py
# (sha256 1b34531fe2deadeb…, 44 327 байт). Взяты строки 1–283 (разделы 1–8) без изменений; раздел 9
# («нормы РК», +6 предметов, пересчёт дат и вещевого имущества) отброшен: его результатов в базовом
# дампе init/10_full.sql нет. Версия скрипта, которой была собрана база, на диске не найдена.
"""Переводит свою бригаду с российских стандартов на казахстанские (ВС РК).
Запуск после enrich.py и functions.sql: python kz_localize.py DSN
Что меняет: ФИО (казахские в основном), национальности и места рождения (области РК), ИИН,
звания по Закону РК «О воинской службе и статусе военнослужащих» (без прапорщиков, профессиональные сержанты по классам),
мотострелковые подразделения -> механизированные, РФ -> РК, категории годности, образование, вид службы, склады."""
import sys, random, datetime as dt
import psycopg2
from psycopg2.extras import execute_values

random.seed(2027)
con = psycopg2.connect(sys.argv[1]); cur = con.cursor()


def q(sql, a=None):
    cur.execute(sql, a); return cur.fetchall()


def wchoice(pairs):
    v, w = zip(*pairs); return random.choices(v, w)[0]


# ---------------------------------------------------------------- имена
KZ_FIRST = ['Ерлан', 'Нурлан', 'Асхат', 'Ержан', 'Данияр', 'Дамир', 'Арман', 'Азамат', 'Айдос', 'Айбек', 'Бауыржан', 'Болат', 'Галым',
            'Даурен', 'Дастан', 'Ермек', 'Ерболат', 'Жандос', 'Жасулан', 'Жанибек', 'Кайрат', 'Канат', 'Мейрам', 'Мурат', 'Нуржан',
            'Нурсултан', 'Олжас', 'Рустем', 'Руслан', 'Самат', 'Санжар', 'Серик', 'Талгат', 'Тимур', 'Улан', 'Ербол', 'Аскар', 'Алибек',
            'Алмас', 'Арсен', 'Бекзат', 'Бахытжан', 'Габит', 'Ильяс', 'Мадияр', 'Магжан', 'Нурбол', 'Абылай', 'Адилет', 'Айдар',
            'Акылбек', 'Алихан', 'Амир', 'Ансар', 'Асет', 'Батыр', 'Бекжан', 'Берик', 'Динмухамед', 'Ельдар', 'Еркебулан', 'Жанат',
            'Нурдаулет', 'Мирас', 'Медет', 'Мухтар', 'Рахат', 'Сабит', 'Сайран', 'Темирлан', 'Чингиз', 'Шынгыс', 'Ерасыл', 'Бекарыс',
            'Диас', 'Нуркен', 'Ерсултан', 'Асылбек', 'Акжол', 'Куаныш', 'Марат', 'Максат', 'Аслан', 'Елдос']
KZ_FATHER = ['Ерлан', 'Нурлан', 'Асхат', 'Ержан', 'Болат', 'Серик', 'Канат', 'Кайрат', 'Марат', 'Мурат', 'Талгат', 'Бахыт', 'Жумабек',
             'Амангельды', 'Бакыт', 'Сапар', 'Есен', 'Куаныш', 'Нуржан', 'Жаксылык', 'Бекет', 'Тулеген', 'Сагат', 'Аскар', 'Галым',
             'Мейрам', 'Самат', 'Бауыржан', 'Абай', 'Даулет', 'Ерик', 'Жанат', 'Рахим', 'Саят', 'Темир', 'Уали', 'Хамит', 'Габит',
             'Дулат', 'Ермек', 'Касым', 'Мухтар', 'Нургали', 'Омар', 'Рустем', 'Айдар', 'Бекзат', 'Медет']
KZ_LAST = ['Абдрахманов', 'Абенов', 'Абдуллин', 'Ахметов', 'Айтбаев', 'Алимжанов', 'Амиров', 'Ашимов', 'Байжанов', 'Бекмуханов',
           'Бектасов', 'Бисенов', 'Бокейханов', 'Габдуллин', 'Джаксыбеков', 'Дюсенов', 'Ергалиев', 'Есенов', 'Жакупов', 'Жанабаев',
           'Жумабаев', 'Жунусов', 'Иманбаев', 'Исмаилов', 'Кабдолов', 'Касымов', 'Каиржанов', 'Калиев', 'Кенжебаев', 'Кудайбергенов',
           'Кусаинов', 'Мамыров', 'Мусин', 'Мухамеджанов', 'Нурпеисов', 'Нургалиев', 'Нуртазин', 'Оспанов', 'Омаров', 'Рахимов',
           'Садыков', 'Сапаров', 'Сарсенбаев', 'Сатпаев', 'Сейткали', 'Серикбаев', 'Смагулов', 'Сулейменов', 'Тажибаев', 'Тасмагамбетов',
           'Токаев', 'Тулегенов', 'Утебаев', 'Ахмединов', 'Шаймерденов', 'Шарипов', 'Ыскаков', 'Ермеков', 'Жаксылыков', 'Байтурсынов',
           'Бекбосынов', 'Доскалиев', 'Елеусизов', 'Есимов', 'Жарылгапов', 'Ибраев', 'Курманов', 'Маратов', 'Нуржанов', 'Оразбаев',
           'Рысбеков', 'Сагинтаев', 'Тлеубаев', 'Уалиханов', 'Хасенов', 'Шакенов', 'Абылкасымов', 'Ажибаев', 'Акимов', 'Алдабергенов',
           'Байкенов', 'Бегалиев', 'Дауренбеков', 'Жолдасбеков', 'Кенесов', 'Мукашев', 'Нысанбаев', 'Онгарбаев', 'Сыздыков', 'Темирханов',
           'Турсунов', 'Утепов', 'Шалабаев', 'Ергазин', 'Мырзахметов', 'Кожахметов', 'Толеуов', 'Байдильдин', 'Нурмаганбетов', 'Аубакиров']
KZ_LAST_UL = ['Серікұлы', 'Болатұлы', 'Ерланұлы', 'Нұрланұлы', 'Қайратұлы', 'Маратұлы', 'Асқарұлы', 'Бақытұлы', 'Ғалымұлы', 'Жанатұлы']
RU_FIRST = ['Александр', 'Дмитрий', 'Сергей', 'Андрей', 'Алексей', 'Евгений', 'Максим', 'Иван', 'Денис', 'Владимир', 'Артём', 'Виталий',
            'Константин', 'Олег', 'Павел', 'Роман', 'Никита', 'Игорь', 'Вадим', 'Станислав']
RU_FATHER = ['Александрович', 'Сергеевич', 'Владимирович', 'Николаевич', 'Викторович', 'Юрьевич', 'Андреевич', 'Петрович', 'Олегович',
             'Геннадьевич', 'Валерьевич', 'Игоревич']
RU_LAST = ['Иванов', 'Кузнецов', 'Смирнов', 'Попов', 'Васильев', 'Петров', 'Соколов', 'Михайлов', 'Новиков', 'Фёдоров', 'Морозов',
           'Волков', 'Лебедев', 'Козлов', 'Степанов', 'Николаев', 'Орлов', 'Макаров', 'Захаров', 'Зайцев', 'Павлов', 'Семёнов',
           'Голубев', 'Виноградов', 'Богданов']
UA_LAST = ['Шевченко', 'Бондаренко', 'Коваленко', 'Ткаченко', 'Кравченко', 'Мельник', 'Бойко', 'Савченко', 'Литвиненко']
DE_LAST = ['Шмидт', 'Миллер', 'Вагнер', 'Беккер', 'Келлер', 'Шнайдер', 'Фишер', 'Гербер', 'Клейн', 'Вебер']
KR_LAST = ['Ким', 'Пак', 'Ли', 'Цой', 'Хан', 'Тен', 'Шин', 'Югай', 'Огай']
UZ_FIRST = ['Шерзод', 'Бахтиёр', 'Ойбек', 'Жамшид', 'Рустам', 'Фаррух', 'Улугбек', 'Шухрат', 'Достон', 'Акмал', 'Санжар', 'Нодир']
UZ_FATHER = ['Рахимжан', 'Абдулла', 'Хасан', 'Махмуд', 'Шавкат', 'Азиз', 'Карим', 'Тахир', 'Илхом', 'Бахром']
UZ_LAST = ['Юлдашев', 'Каримов', 'Рахимов', 'Хасанов', 'Мирзаев', 'Абдуллаев', 'Турсунов', 'Исмаилов', 'Усманов', 'Назаров', 'Холматов']
UG_FIRST = ['Ильхам', 'Мурат', 'Арслан', 'Дильмурат', 'Шамиль', 'Ерзат', 'Азат', 'Кадыр', 'Нурмамат', 'Аблет']
UG_LAST = ['Масимов', 'Нурахунов', 'Розахунов', 'Сабиров', 'Мамутов', 'Ахметжанов', 'Тохтиев', 'Исмаилов', 'Хамраев', 'Юнусов']
TT_FIRST = ['Ринат', 'Рамиль', 'Ильдар', 'Тимур', 'Рустам', 'Айрат', 'Марат', 'Рафаэль']
TT_LAST = ['Галиев', 'Хабибуллин', 'Сафин', 'Гарипов', 'Валиев', 'Шарафутдинов', 'Ахметшин', 'Закиров']
AZ_FIRST = ['Эльвин', 'Рашад', 'Тельман', 'Самир', 'Фарид', 'Эльчин']
AZ_LAST = ['Алиев', 'Гусейнов', 'Мамедов', 'Гасанов', 'Керимов', 'Велиев']
TR_FIRST = ['Мехмет', 'Ахмет', 'Али', 'Исмет', 'Эркан']
TR_LAST = ['Османов', 'Шахбазов', 'Курбанов', 'Ибрагимов', 'Мустафаев']


def patr_from(father):
    """Ерлан -> Ерланович; Бакыт -> Бакытович; Абай -> Абаевич; Есен -> Есенович."""
    if father.endswith('й'):
        return father[:-1] + 'евич'
    if father.endswith(('а', 'я')):
        return father[:-1] + 'ович'
    if father.endswith(('ы', 'и')):
        return father + 'евич'
    if father.endswith(('ж', 'ш', 'ч', 'щ', 'ц')):
        return father + 'евич'
    return father + 'ович'


def kz_ul(father):
    """Ерлан -> Ерланұлы (казахская форма отчества)."""
    m = {'Нурлан': 'Нұрлан', 'Кайрат': 'Қайрат', 'Аскар': 'Асқар', 'Бакыт': 'Бақыт', 'Галым': 'Ғалым', 'Куаныш': 'Қуаныш',
         'Касым': 'Қасым', 'Нургали': 'Нұрғали', 'Жаксылык': 'Жақсылық', 'Бахыт': 'Бақыт', 'Габит': 'Ғабит'}
    return m.get(father, father) + 'ұлы'


def fio(nat):
    if nat == 'казах':
        father = random.choice(KZ_FATHER)
        if random.random() < 0.08:          # фамилия по казахской традиции: Серікұлы
            last = random.choice(KZ_LAST_UL)
        else:
            last = random.choice(KZ_LAST)
        patr = kz_ul(father) if random.random() < 0.25 else patr_from(father)
        return last, random.choice(KZ_FIRST), patr
    if nat == 'узбек':
        return random.choice(UZ_LAST), random.choice(UZ_FIRST), patr_from(random.choice(UZ_FATHER))
    if nat == 'уйгур':
        return random.choice(UG_LAST), random.choice(UG_FIRST), patr_from(random.choice(UZ_FATHER + ['Ильхам', 'Аблет']))
    if nat == 'татарин':
        return random.choice(TT_LAST), random.choice(TT_FIRST), random.choice(['Ринатович', 'Рашидович', 'Маратович', 'Ильдарович', 'Равильевич'])
    if nat == 'азербайджанец':
        return random.choice(AZ_LAST), random.choice(AZ_FIRST), random.choice(['Ильхамович', 'Рашидович', 'Тофикович', 'Гусейнович'])
    if nat == 'турок':
        return random.choice(TR_LAST), random.choice(TR_FIRST), random.choice(['Исмаилович', 'Мехметович', 'Османович'])
    if nat == 'украинец':
        return random.choice(UA_LAST), random.choice(RU_FIRST), random.choice(RU_FATHER)
    if nat == 'немец':
        return random.choice(DE_LAST), random.choice(RU_FIRST + ['Виктор', 'Эдуард', 'Артур']), random.choice(RU_FATHER + ['Эдуардович', 'Генрихович'])
    if nat == 'кореец':
        return random.choice(KR_LAST), random.choice(RU_FIRST + ['Вячеслав', 'Эдуард']), random.choice(RU_FATHER)
    return random.choice(RU_LAST), random.choice(RU_FIRST), random.choice(RU_FATHER)


# доли примерно по переписи РК 2021, казахов в армии больше
NAT_KZ = [('казах', 80), ('русский', 9), ('узбек', 3.5), ('уйгур', 1.8), ('татарин', 1), ('украинец', 1), ('немец', 0.8),
          ('кореец', 0.7), ('азербайджанец', 0.6), ('турок', 0.6)]
REG_KZ = [('г. Астана', 7), ('г. Алматы', 8), ('г. Шымкент', 6), ('Туркестанская обл.', 12), ('Алматинская обл.', 8),
          ('Жамбылская обл.', 7), ('Кызылординская обл.', 6), ('Карагандинская обл.', 5), ('Актюбинская обл.', 5), ('Атырауская обл.', 4),
          ('Мангистауская обл.', 4), ('Западно-Казахстанская обл.', 4), ('Костанайская обл.', 3.5), ('Акмолинская обл.', 3),
          ('Павлодарская обл.', 3), ('Северо-Казахстанская обл.', 2), ('Восточно-Казахстанская обл.', 3), ('область Абай', 3),
          ('область Жетісу', 3), ('область Ұлытау', 1)]
REG_SLAV = [('Костанайская обл.', 14), ('Северо-Казахстанская обл.', 13), ('Павлодарская обл.', 12), ('Карагандинская обл.', 12),
            ('Восточно-Казахстанская обл.', 13), ('Акмолинская обл.', 11), ('г. Астана', 8), ('г. Алматы', 10), ('область Абай', 4)]
NAT_REG = {'узбек': [('Туркестанская обл.', 60), ('г. Шымкент', 30), ('Жамбылская обл.', 10)],
           'уйгур': [('Алматинская обл.', 55), ('г. Алматы', 35), ('область Жетісу', 10)],
           'кореец': [('г. Алматы', 40), ('Кызылординская обл.', 25), ('Алматинская обл.', 20), ('Карагандинская обл.', 15)],
           'турок': [('Жамбылская обл.', 50), ('Туркестанская обл.', 30), ('Алматинская обл.', 20)],
           'азербайджанец': [('Жамбылская обл.', 35), ('Туркестанская обл.', 30), ('г. Алматы', 35)],
           'татарин': REG_SLAV, 'русский': REG_SLAV, 'украинец': REG_SLAV, 'немец': REG_SLAV}


def iin(bdate, sex, serial):
    """ИИН РК: ГГММДД + век/пол + 4 цифры + контрольная (алгоритм с двумя наборами весов)."""
    c = (5 if sex == 'М' else 6) if bdate.year >= 2000 else (3 if sex == 'М' else 4)
    for shift in range(100):
        body = f'{bdate:%y%m%d}{c}{(serial + shift * 7919) % 10000:04d}'
        d = list(map(int, body))
        k = sum(x * w for x, w in zip(d, range(1, 12))) % 11
        if k == 10:
            k = sum(x * w for x, w in zip(d, [3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2])) % 11
        if k != 10:
            return body + str(k)


# ---------------------------------------------------------------- 1. схема: снимаем FK, чтобы переименовать ключи
fks = q("""SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) FROM pg_constraint
           WHERE contype='f' AND confrelid IN ('mil_core.rank'::regclass, 'mil_core."position"'::regclass, 'mil_core.unit'::regclass)""")
for t, n, _ in fks:
    cur.execute(f'ALTER TABLE {t} DROP CONSTRAINT {n}')

cur.execute("""
ALTER TABLE mil_core.unit DROP CONSTRAINT IF EXISTS unit_country_check;
ALTER TABLE mil_core."position" DROP CONSTRAINT IF EXISTS position_army_check;
ALTER TABLE mil_core.rank DROP CONSTRAINT IF EXISTS rank_army_check;
ALTER TABLE mil_core.rank DROP CONSTRAINT IF EXISTS rank_category_check;
ALTER TABLE mil_core.person_profile DROP CONSTRAINT IF EXISTS person_profile_service_type_check;""")

# ---------------------------------------------------------------- 2. РФ -> РК
for t, c in [('unit', 'country'), ('rank', 'army'), ('position', 'army'), ('kit', 'army')]:
    cur.execute(f"UPDATE mil_core.\"{t}\" SET {c}='РК' WHERE {c}='РФ'")
cur.execute("UPDATE mil_core.vehicle SET factory_no = 'РК' || substr(factory_no, 3) WHERE factory_no LIKE 'РФ-%'")
cur.execute("UPDATE mil_core.item SET country = 'СССР/Россия (производитель)' WHERE country = 'СССР/РФ'")

# ---------------------------------------------------------------- 3. мотострелковые -> механизированные (как в ВС РК)
WORDS = [('мотострелковая', 'механизированная'), ('мотострелковой', 'механизированной'), ('мотострелковый', 'механизированный'),
         ('мотострелкового', 'механизированного'), ('мотострелковое', 'механизированное'), ('Мотострелки', 'Мотопехота')]
def rep_sql(col):
    s = col
    for a, b in WORDS:
        s = f"replace({s}, '{a}', '{b}')"
    return s
for t, c in [('unit', 'full_name'), ('position', 'position_name'), ('staff_position', 'position_name'), ('position_kit', 'position_name'),
             ('vehicle_crew_role', 'role_name'), ('crew_assignment', 'seat')]:
    if q("SELECT 1 FROM information_schema.columns WHERE table_schema='mil_core' AND table_name=%s AND column_name=%s", (t, c)):
        cur.execute(f'UPDATE mil_core."{t}" SET {c} = {rep_sql(c)} WHERE {c} ~ \'отострел\'')
# мсб/мср/мсв/мсо -> мехб/мехр/мехв/мехо
cur.execute(r"UPDATE mil_core.unit SET short_name = regexp_replace(short_name, '\mмс([брво])\M', 'мех\1') WHERE short_name ~ '\mмс[брво]\M'")

# верхние звенья
TOP = {'20.': ('ВС РК', 'Вооружённые Силы Республики Казахстан', None),
       '20.0.': ('СВ ВС РК', 'Сухопутные войска Вооружённых Сил Республики Казахстан', None),
       '20.0.6.': ('УК', 'условное командование', 'Региональное командование'),
       '20.0.6.0.': ('ОА (усл.)', 'общевойсковое объединение (условное звено из ПМИ, в ВС РК нет)', None),
       '20.0.6.0.0.': ('АК (усл.)', 'армейский корпус (условное звено из ПМИ)', None),
       '20.0.6.0.0.2.': ('бр', 'механизированная бригада (промежуточно)', None)}
for code, (sn, fn, lvl) in TOP.items():
    cur.execute('UPDATE mil_core.unit SET short_name=%s, full_name=%s, level_name=COALESCE(%s, level_name) WHERE unit_code=%s', (sn, fn, lvl, code))

# ---------------------------------------------------------------- 4. звания ВС РК
cur.execute("""INSERT INTO mil_core.rank (rank_name, category, army, sort_order) VALUES
  ('сержант третьего класса','сержанты','РК',6), ('сержант второго класса','сержанты','РК',7), ('сержант первого класса','сержанты','РК',8),
  ('штаб-сержант','сержанты','РК',9), ('мастер-сержант','сержанты','РК',10) ON CONFLICT DO NOTHING""")
staff = q("""SELECT s.staff_id, s.rank_name, s.position_name, pp.service_type FROM mil_core.staff_position s
             JOIN mil_core.unit u USING (unit_code) LEFT JOIN mil_core.person_profile pp USING (person_id)
             WHERE u.country='РК'""")
new_rank = []
for sid, rank, pos, st in staff:
    contract = st == 'по контракту'
    r = rank
    if rank == 'старший прапорщик':
        r = 'штаб-сержант'
    elif rank == 'прапорщик':
        r = 'сержант первого класса' if 'Старшина' in pos or random.random() < 0.5 else 'сержант второго класса'
    elif rank == 'старшина':
        r = 'сержант первого класса'
    elif contract and rank == 'старший сержант':
        r = 'сержант второго класса'
    elif contract and rank in ('сержант', 'младший сержант'):
        r = 'сержант третьего класса' if random.random() < 0.7 else 'сержант второго класса'
    if r != rank:
        new_rank.append((sid, r))
execute_values(cur, 'UPDATE mil_core.staff_position s SET rank_name=v.r FROM (VALUES %s) v(id, r) WHERE s.staff_id=v.id', new_rank)
# главный сержант бригады
cur.execute("""UPDATE mil_core.staff_position SET rank_name='мастер-сержант' WHERE staff_id = (
  SELECT staff_id FROM mil_core.staff_position WHERE unit_code LIKE '20.0.6.0.0.2.%' AND rank_name='штаб-сержант' ORDER BY unit_code, staff_id LIMIT 1)""")
cur.execute("DELETE FROM mil_core.rank WHERE army='РК' AND rank_name IN ('прапорщик','старший прапорщик','старшина') "
            "AND rank_name NOT IN (SELECT rank_name FROM mil_core.staff_position)")
order = ['рядовой', 'ефрейтор', 'младший сержант', 'сержант', 'старший сержант', 'сержант третьего класса', 'сержант второго класса',
         'сержант первого класса', 'штаб-сержант', 'мастер-сержант', 'лейтенант', 'старший лейтенант', 'капитан', 'майор', 'подполковник', 'полковник']
for i, r in enumerate(order, 1):
    cur.execute("UPDATE mil_core.rank SET sort_order=%s WHERE rank_name=%s AND army='РК'", (i, r))

# ---------------------------------------------------------------- 5. люди: ФИО, национальность, место рождения, ИИН
cur.execute('ALTER TABLE mil_core.person_profile ADD COLUMN IF NOT EXISTS iin TEXT')
cur.execute("COMMENT ON COLUMN mil_core.person_profile.iin IS 'ИИН (12 цифр, с верной контрольной суммой; вымышленный). Для военнослужащих США NULL'")
people = q("""SELECT p.person_id, pp.birth_date, pp.sex FROM mil_core.person p JOIN mil_core.staff_position s USING (person_id)
              JOIN mil_core.unit u USING (unit_code) JOIN mil_core.person_profile pp USING (person_id) WHERE u.country='РК' ORDER BY p.person_id""")
names, prof = [], []
for pid, bdate, sex in people:
    nat = wchoice(NAT_KZ)
    last, first, patr = fio(nat)
    place = wchoice(NAT_REG.get(nat, REG_KZ))
    names.append((pid, last, first, patr))
    prof.append((pid, nat, place, iin(bdate, sex, pid * 37 % 10000)))
execute_values(cur, 'UPDATE mil_core.person p SET last_name=v.l, first_name=v.f, patronymic=v.m FROM (VALUES %s) v(id,l,f,m) WHERE p.person_id=v.id', names)
execute_values(cur, 'UPDATE mil_core.person_profile p SET nationality=v.n, birthplace=v.b, iin=v.i FROM (VALUES %s) v(id,n,b,i) WHERE p.person_id=v.id', prof)

# годность (категории ВВК МО РК), образование, вид службы
cur.execute("""UPDATE mil_core.person_profile p SET
   fitness_category = CASE fitness_category WHEN 'А' THEN 'А (годен)' WHEN 'Б-3' THEN 'Б (годен с незначительными ограничениями)'
                      WHEN 'Б-4' THEN 'Б (годен с незначительными ограничениями)' ELSE fitness_category END,
   education = CASE education WHEN 'среднее профессиональное' THEN 'техническое и профессиональное' WHEN 'среднее общее' THEN 'общее среднее'
               WHEN 'высшее военное' THEN 'высшее военное' ELSE education END,
   service_type = CASE service_type WHEN 'по призыву' THEN 'срочная воинская служба' ELSE service_type END
 FROM mil_core.staff_position s JOIN mil_core.unit u USING (unit_code)
 WHERE s.person_id=p.person_id AND u.country='РК'""")

# ---------------------------------------------------------------- 6. склады
cur.execute("""UPDATE mil_core.warehouse SET warehouse_name='Склад условного командования (вышестоящий)',
               capacity_note='условный резерв, все виды' WHERE warehouse_name LIKE 'Окружной склад%'""")
cur.execute("UPDATE mil_core.warehouse SET warehouse_name='Склад объединения (вышестоящий, условно)' WHERE warehouse_name='Склад армии (вышестоящий)'")

# ---------------------------------------------------------------- 7. возвращаем FK
for t, n, d in fks:
    cur.execute(f'ALTER TABLE {t} ADD CONSTRAINT {n} {d}')

cur.execute("""
ALTER TABLE mil_core.unit ADD CONSTRAINT unit_country_check CHECK (country IN ('РК','США'));
ALTER TABLE mil_core."position" ADD CONSTRAINT position_army_check CHECK (army IN ('РК','США'));
ALTER TABLE mil_core.rank ADD CONSTRAINT rank_army_check CHECK (army IN ('РК','США'));
ALTER TABLE mil_core.rank ADD CONSTRAINT rank_category_check CHECK (category IN ('солдаты','сержанты','офицеры'));
ALTER TABLE mil_core.person_profile ADD CONSTRAINT person_profile_service_type_check
  CHECK (service_type IN ('срочная воинская служба','по контракту','офицер кадра'));""")

# ---------------------------------------------------------------- 8. представления
cur.execute("""DROP VIEW IF EXISTS mil_core.v_unit_staff_by_category;
CREATE VIEW mil_core.v_unit_staff_by_category AS
 SELECT t.root_code AS unit_code, count(*) AS staff_total,
    count(*) FILTER (WHERE r.category = 'офицеры') AS officers,
    count(*) FILTER (WHERE r.category = 'сержанты' AND r.rank_name IN ('сержант третьего класса','сержант второго класса',
                     'сержант первого класса','штаб-сержант','мастер-сержант')) AS prof_sergeants,
    count(*) FILTER (WHERE r.category = 'сержанты') AS sergeants,
    count(*) FILTER (WHERE r.category = 'солдаты') AS soldiers
   FROM mil_core.v_unit_tree t JOIN mil_core.staff_position s ON s.unit_code = t.unit_code JOIN mil_core.rank r USING (rank_name)
  GROUP BY t.root_code""")
vdef = q("SELECT pg_get_viewdef('mil_core.v_person')")[0][0].rstrip().rstrip(';')
if 'pp.iin' not in vdef:
    # новая колонка в конец списка SELECT (CREATE OR REPLACE разрешает только добавлять в конец)
    i = vdef.upper().index('\n   FROM ')
    cur.execute(f'CREATE OR REPLACE VIEW mil_core.v_person AS {vdef[:i]},\n    pp.iin {vdef[i:]}')


con.commit()
print('KZ_OK', len(names), 'человек,', len(new_rank), 'званий изменено')
