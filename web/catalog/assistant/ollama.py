"""Планировщик с локальной языковой моделью через Ollama (без внешнего API и без оплаты).

Подключается настройкой ASSISTANT_PROVIDER='catalog.assistant.ollama.OllamaPlanner'.
Модель получает только описания инструментов и список доступных пользователю округов.
SQL, схему базы и чужие округа она не видит: инструменты выполняет engine.py после проверки прав.

Два обращения к модели на вопрос:
  1. plan()    — модель выбирает инструменты и параметры;
  2. compose() — модель пишет короткий ответ только по таблицам, которые вернули инструменты.
Если модель недоступна, engine.py переключается на KeywordPlanner.
"""
import json
import re
import urllib.error
import urllib.request

from django.conf import settings

from . import tools
from .planner import KeywordPlanner

MAX_TABLE_ROWS = 30   # строк таблицы, которые видит модель при ответе
FOREIGN_SCRIPT = re.compile(r'[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]')   # китайский, японский, корейский
# Казахские названия округов -> русская основа названия (как в short_name).
KAZAKH_NAMES = {'шығыс': 'восток', 'батыс': 'запад', 'оңтүстік': 'юг'}
# Английские названия округов (целым словом: «east», но не «least»).
ENGLISH_NAMES = {'east': 'восток', 'eastern': 'восток', 'west': 'запад', 'western': 'запад',
                 'south': 'юг', 'southern': 'юг'}

PLAN_PROMPT = """Ты — помощник учебной базы данных по военным округам (региональным командованиям) Казахстана.
Все данные учебные. Твоя задача на этом шаге — выбрать инструменты, которые дадут данные для ответа.
Правила:
- Вызывай инструменты, а не отвечай по памяти. Числа знают только инструменты.
- Параметр district — это КОД округа из списка ниже (например ОКР-АСТ), а не название.
- «Астана», «Восток», «Запад», «Юг» и их формы («на Востоке», «Астаны») — это округа из списка.
  По-казахски: Шығыс = Восток, Батыс = Запад, Оңтүстік = Юг, Астана = Астана.
  Казахские слова: қанша адам = сколько людей, ең көп / ең аз = больше / меньше всего, жетіспейді / тапшылық =
  не хватает (district_supply с only_deficit=true), запас / қамтамасыз етілуі = обеспеченность, рота = рота.
  По-английски: East = Восток, West = Запад, South = Юг, Astana = Астана; коды латиницей переводи в кириллицу:
  VOS-1 = ВОС-1, ZAP-2 = ЗАП-2, YUG-3 = ЮГ-3, AST-1 = АСТ-1, OKR-AST = ОКР-АСТ. Слова: battalion = батальон,
  company = рота, platoon = взвод, squad = отделение, mortar = миномёт, tank = танк, supply = обеспеченность,
  shortage / lacking = не хватает (district_supply с only_deficit=true), how many people = сколько людей,
  range / speed / weight / specifications / characteristics = ТТХ (item_card).
- Вопрос про все округа или «где больше/меньше» — compare_districts с нужным metric.
- Численность и общая сводка по округу — district_summary.
- Соединения (бригады) округа и сколько в них батальонов, рот, взводов, отделений — district_formations.
  Структура одной бригады (какие батальоны и роты) — formation_structure с кодом соединения
  (АСТ-1…3, ВОС-1…3, ЗАП-1…3, ЮГ-1…3; цифра — номер соединения в округе).
- Структура везде «по три»: в бригаде 3 батальона (в артиллерии — дивизионы), в батальоне 3 роты (батареи),
  в роте 3 взвода, во взводе 3 отделения (экипажа, расчёта). Других подразделений (управления бригады,
  отдельных рот и взводов обеспечения, миномётных батарей) в базе нет — если о них спрашивают, так и скажи.
- Сколько людей, какие должности и какая техника в бригаде, батальоне, роте, взводе или отделении —
  unit_composition: formation — код бригады, затем номера battalion, company, platoon, squad (что известно).
  «8-я танковая рота ВОС-1» -> formation=ВОС-1, company=8. «Взвод управления 1-й батареи АСТ-3» ->
  formation=АСТ-3, battalion=1, company=1, platoon=3. «Танковый батальон ВОС-1» (в механизированной бригаде
  это 3-й батальон) -> formation=ВОС-1, battalion=3. Вопрос про подразделение — это unit_composition, а не item_card.
  Батальон, названный словами, а не номером («реактивный дивизион АСТ-3», «танковый батальон ЮГ-1»), —
  unit_name с этим названием и formation.
  ВАЖНО: передавай только уровни, названные в вопросе. Вопрос про батальон — только formation и battalion;
  про бригаду — только formation; company, platoon, squad — только если их назвали.
  Если спрашивают про конкретный образец или должность («сколько танков», «сколько БМП», «кто командир») —
  передай search с этим словом (танк, БМП, командир).
- Состав одинаков во всех бригадах своего рода. Если бригада не названа: механизированное отделение —
  formation=ВОС-1, battalion=1, company=1, platoon=1, squad=1; танковый экипаж — formation=ВОС-1, company=7,
  platoon=1, squad=2; расчёт САУ — formation=АСТ-3, battalion=1, company=1, platoon=1, squad=1.
- Характеристики образца (ТТХ: запас хода, скорость, масса, калибр, экипаж) — item_card с названием образца;
  find_item — только если спрашивают, есть ли такой образец в каталоге.
- Если спрашивают про округ, которого нет в списке доступных ниже, не вызывай инструменты и ответь, что к этому
  округу у пользователя нет доступа, и назови доступные.
- Можно вызвать до 4 инструментов за раз, например один и тот же для двух округов.
- Короткий уточняющий вопрос («а на Востоке?», «а в ЮГ-1?», «а танков?») продолжает прошлый вопрос из диалога: возьми из него, что именно спрашивали, и вызови нужный инструмент заново.
- Если вопрос не про эти данные (приветствие, посторонняя тема), не вызывай инструменты и коротко
  ответь, о чём можно спросить.
- Если отвечаешь сам, без инструментов, — отвечай на языке вопроса (русский, казахский или английский).
Доступные пользователю округа:
{districts}"""

ANSWER_PROMPT = """Ты — помощник учебной базы данных по военным округам Казахстана. Все данные учебные.
Напиши ответ на вопрос пользователя на языке вопроса, 1–4 полных предложения: на русский вопрос — по-русски,
на казахский — по-казахски, на английский — по-английски. Других языков не используй.
Правила:
- Используй ТОЛЬКО числа и названия из таблиц ниже, ничего не придумывай.
- Всегда называй, что это за число, к какому округу оно относится и в каких единицах. Не отвечай голым числом.
- Не складывай числа сам. Если строк несколько, назови подходящие строки с их значениями.
- Если в таблице есть строка «Итого» или поле note с итогами («Всего …»), максимумом и минимумом — бери числа
  оттуда и обязательно назови итог.
- Вопрос про округ целиком — отвечай по округу целиком (строка «Итого по округу»), а не по одной бригаде.
- Поиск по названию может вернуть лишние строки (например «противотанковая пушка» на запрос «танк»):
  упоминай только строки, которые действительно отвечают на вопрос.
- В таблицах запасов «%» и «Обеспеченность, %» — это наличие от нормы, а не дефицит. Строки идут от худшей
  обеспеченности к лучшей: начинай с первых строк.
- Таблицы пользователь видит под ответом, поэтому не переписывай их целиком — выдели главное.
- Не упоминай таблицы, поля, «note», «строку Итого» и источники данных: просто отвечай на вопрос.
- Пиши на одном языке: не вставляй английские названия полей (personnel, supply и т. п.) в русский или
  казахский ответ.
- Первое предложение — сразу ответ. Не пиши, на каком языке вопрос или ответ, не повторяй и не переводи вопрос,
  не начинай со слов «Вопрос:» и «Ответ:».
- Если в таблицах нет ответа на вопрос, так и скажи."""


class ModelUnavailable(Exception):
    pass


def _ollama_tools():
    return [{'type': 'function', 'function': {
        'name': s['name'], 'description': s['description'], 'parameters': s['input_schema']}}
        for s in tools.schemas()]


def _clean_args(name, args):
    """Модель может прислать лишние ключи, пустые значения или 'true' строкой — приводим к схеме.
    Проверка прав и обязательных параметров остаётся в tools.run()."""
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except ValueError:
            args = {}
    if not isinstance(args, dict) or name not in tools.TOOLS:
        return {}
    props = tools.TOOLS[name][2]
    clean = {}
    for key, value in args.items():
        if key not in props or value in (None, ''):
            continue
        if props[key].get('type') == 'boolean' and isinstance(value, str):
            value = value.strip().lower() in ('true', '1', 'да', 'yes')
        clean[key] = value
    return clean


KAZAKH_LETTERS = set('әғқңөұүһі')
# Русские служебные слова, которых нет в казахском тексте.
RUSSIAN_WORDS = {'и', 'в', 'во', 'из', 'них', 'на', 'по', 'что', 'это', 'от', 'для', 'при', 'составляет', 'там', 'тут',
                 'сколько', 'как', 'где', 'какой', 'какая', 'еще', 'ещё', 'тоже', 'там',
                 'человек', 'человека', 'есть', 'всего', 'который', 'которые', 'а', 'но', 'же', 'также'}


def is_kazakh(text):
    """Вопрос на казахском: есть буквы, которых нет в русском алфавите."""
    return bool(KAZAKH_LETTERS & set(str(text).casefold()))


def language(text):
    """'kk' — казахский, 'en' — английский (латиницы больше, чем кириллицы), иначе 'ru'.
    Коды вроде ВОС-1 и названия вроде Т-72Б в английском тексте не мешают: латиницы там всё равно больше."""
    text = str(text)
    if is_kazakh(text):
        # казахские названия внутри русского ответа («Шығыс округінде … Из них 358 офицеров») — это русский ответ
        words = re.findall(r'\w+', re.sub(r'«[^»]*»', ' ', text.casefold()))
        kazakh = sum(bool(KAZAKH_LETTERS & set(w)) for w in words)
        russian = sum(w in RUSSIAN_WORDS for w in words)
        return 'kk' if kazakh >= russian else 'ru'
    latin = len(re.findall(r'[A-Za-z]', text))
    cyrillic = len(re.findall(r'[А-Яа-яЁё]', text))
    return 'en' if latin > cyrillic else 'ru'


def question_language(question, history=()):
    """Язык вопроса с учётом чата: короткое уточнение без явных признаков («Ал Батыста ше?» — казахский без
    особых букв) наследует язык предыдущего вопроса. Русское уточнение («а на Востоке?») узнаётся по служебным словам."""
    lang = language(question)
    words = re.findall(r'\w+', str(question).casefold())
    if lang == 'ru' and history and len(words) <= 4 and not any(w in RUSSIAN_WORDS for w in words):
        return language(list(history)[-1][0])
    return lang


LANGUAGE_HINT = {
    'kk': '\n- Вопрос будет на казахском языке: весь ответ пиши на казахском языке (кириллицей), числа и названия '
          'образцов оставь как в таблице. Сразу пиши ответ: не повторяй вопрос и не переводи его.',
    'en': '\n- The question will be in English: write the whole answer in English. Keep numbers as in the tables; '
          'unit codes and equipment names may stay as in the tables (ВОС-1, Т-72Б) or be transliterated (VOS-1, '
          'T-72B). Call the districts Astana, East (Восток), West (Запад), South (Юг). Answer directly, '
          'do not repeat the question.',
    'ru': '',
}
# Вступления о языке и пересказ вопроса («Вопрос на русском, поэтому отвечаю по-русски», «Вопрос: … Ответ: …»).
META_LINE = re.compile(r'^\W*(вопрос|сұрақ|question)\b', re.IGNORECASE)
META_PREFIX = re.compile(r'^\W*(ответ|жауап|answer)\W*:\W*', re.IGNORECASE)
META_SENTENCE = re.compile(r'отвечаю|отвечу|ответ должен|answer (should|must)|жауап бер|аударамын|переведу|перевожу|translat|I(\'ll| will| am going to)? answer|answering in|'
                           r'(вопрос|сұрақ|question)\W+(задан\W+|is\W+|asked\W+)?(на|по|in)\W*'
                           r'(русск|казах|англ|қазақ|орыс|ағылшын|english|russian|kazakh)', re.IGNORECASE)
SENTENCE_END = re.compile(r'(?<=[.!?])\s+|(?<=[.!?]»)\s+')


def strip_meta(text):
    """Убирает из начала ответа фразы о языке, пересказ вопроса и «Ответ:»; сам ответ не трогает."""
    lines = str(text).strip().split('\n')
    while lines:
        line = META_PREFIX.sub('', lines[0].strip())
        sentences = [x for x in SENTENCE_END.split(line) if x]
        while sentences and (META_SENTENCE.search(sentences[0]) or META_LINE.match(sentences[0])
                             or re.fullmatch(r'\W*«[^»]*»\W*', sentences[0])):   # перевод вопроса в кавычках
            sentences.pop(0)
            if sentences:
                sentences[0] = META_PREFIX.sub('', sentences[0])
        if sentences:
            lines[0] = ' '.join(sentences)
            break
        lines.pop(0)
    return '\n'.join(lines).strip() or str(text).strip()     # всё оказалось «служебным» — оставляем как есть


REWRITE = {'kk': 'Перепиши этот ответ на казахском языке.',
           'en': 'Rewrite this answer in English.',
           'ru': 'Перепиши ответ по-русски.'}


def mentioned_districts(question, districts):
    """Коды округов из вопроса: русские формы названий (как в KeywordPlanner) и казахские названия."""
    q = question.casefold()
    for kz, ru in KAZAKH_NAMES.items():
        q = q.replace(kz, ru)
    q = re.sub(r'[a-z]+', lambda m: ENGLISH_NAMES.get(m.group(0), m.group(0)), q)
    return KeywordPlanner._districts(q, districts)


HISTORY_TURNS = 3        # прошлых обменов чата в запросе к модели
HISTORY_CHARS = 600      # ответ из прошлого обмена обрезается до этой длины


class OllamaPlanner:
    history = ()             # прошлые обмены чата [(вопрос, ответ)], задаёт engine.answer

    def _prior(self):
        """Прошлые обмены как диалог: модель понимает уточнения («а на Востоке?», «а в ЮГ-1?»)."""
        out = []
        for question, text in list(self.history)[-HISTORY_TURNS:]:
            out += [{'role': 'user', 'content': str(question)},
                    {'role': 'assistant', 'content': (str(text or '').strip() or '—')[:HISTORY_CHARS]}]
        return out

    def _context(self):
        """Для шага ответа — только предыдущий вопрос: данные уже выбраны, а прошлые ответы заставляют модель
        рассуждать дольше (дороже) и тянут их пересказ в новый ответ."""
        turns = list(self.history)
        if not turns:
            return ''
        return f'Предыдущий вопрос в этом чате (только чтобы понять текущий): {turns[-1][0]}\n'

    def __init__(self):
        self.url = getattr(settings, 'OLLAMA_URL', 'http://host.docker.internal:11434').rstrip('/')
        self.model = getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:14b')
        self.timeout = getattr(settings, 'OLLAMA_TIMEOUT', 120)
        self.mode = f'ИИ · {self.model} (локально)'
        self.direct_text = ''

    def _chat(self, messages, with_tools):
        body = {'model': self.model, 'messages': messages, 'stream': False,
                'options': {'temperature': 0.1, 'num_ctx': 8192}}
        if with_tools:
            body['tools'] = _ollama_tools()
        req = urllib.request.Request(f'{self.url}/api/chat', data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise ModelUnavailable(str(exc)) from exc
        if 'message' not in data:
            raise ModelUnavailable(data.get('error', 'пустой ответ модели'))
        return data['message']

    def plan(self, question, districts):
        listing = '\n'.join(f'- {d["district_code"]}: {d["short_name"]}, штаб {d["hq_city"]}' for d in districts)
        content = question
        mentioned = mentioned_districts(question, districts)
        if mentioned:
            content += '\n[Округа, названные в вопросе: ' + ', '.join(mentioned) + ']'
        msg = self._chat([{'role': 'system', 'content': PLAN_PROMPT.format(districts=listing or '—')}]
                         + self._prior() + [{'role': 'user', 'content': content}], with_tools=True)
        calls = []
        for call in msg.get('tool_calls') or []:
            fn = call.get('function') or {}
            name = fn.get('name', '')
            calls.append((name, _clean_args(name, fn.get('arguments'))))
        if not calls:
            self.direct_text = (msg.get('content') or '').strip()
        return calls

    def compose(self, question, results):
        if not results:
            text = self.direct_text
            lang = question_language(question, self.history)
            if text and language(text) != lang:   # ответ без инструментов не на языке вопроса — переписываем раз
                try:
                    text = strip_meta(self._chat([{'role': 'system', 'content': ANSWER_PROMPT + LANGUAGE_HINT[lang]},
                                                  {'role': 'user', 'content': f'Вопрос: {question}\n\n{REWRITE[lang]}'
                                                                              f'\n\n{text}'}],
                                                 with_tools=False).get('content') or '') or text
                except ModelUnavailable:
                    pass
            return text or KeywordPlanner().compose(question, results)
        # Строки — словари «заголовок: значение»: так модель не путает колонки.
        data = [{'title': t['title'], 'note': t['note'],
                 'rows': [{h: v for h, v in zip(t['headers'], row) if v not in (None, '')}
                          for row in t['rows'][:MAX_TABLE_ROWS]]}
                for t in results]
        lang = question_language(question, self.history)
        messages = [{'role': 'system', 'content': ANSWER_PROMPT + LANGUAGE_HINT[lang]},
                    {'role': 'user', 'content': self._context() + f'Вопрос: {question}\n\nТаблицы:\n'
                                                + json.dumps(data, ensure_ascii=False, default=str)}]
        text = ''
        try:
            usable = ''                   # запасной ответ: верный по сути ответ не на том языке лучше, чем никакого
            for attempt in range(2):      # не тот язык (китайский; другой язык, чем у вопроса) — переспрашиваем раз
                text = strip_meta(self._chat(messages, with_tools=False).get('content') or '')
                if FOREIGN_SCRIPT.search(text):
                    fix = REWRITE[lang]
                elif language(text.replace(question, '')) != lang:   # процитированный вопрос не в счёт
                    fix, usable = REWRITE[lang], text
                else:
                    break
                messages = messages + [{'role': 'assistant', 'content': text}, {'role': 'user', 'content': fix}]
            else:
                text = usable
        except ModelUnavailable:
            text = ''
        return text or KeywordPlanner().compose(question, results)
