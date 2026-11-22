"""Выбор инструментов по вопросу.

KeywordPlanner — запасной режим без языковой модели: работает всегда и не требует сети.
Провайдер с языковой моделью подключается через settings.ASSISTANT_PROVIDER и обязан
реализовать тот же метод plan(question, districts) -> [(tool, args), ...].
"""
import re

METRIC_WORDS = {
    'personnel': ('числен', 'человек', 'людей', 'личн', 'офицер', 'сержант', 'солдат', 'адам', 'қанша', 'жеке құрам'),
    'equipment': ('техник', 'вооруж', 'танк', 'машин', 'оруди', 'бмп', 'бтр', 'қару', 'техника'),
    'supply': ('запас', 'обеспеч', 'дефицит', 'нехват', 'склад', 'горюч', 'топлив', 'боеприп', 'продовол', 'вещев', 'қор'),
    'formations': ('состав', 'соединен', 'бригад', 'батальон', 'дивизион', 'взвод', 'отделени', 'құрам'),
}
COMPARE_WORDS = ('сравн', 'все округ', 'всех округ', 'по округам', 'где больше', 'где меньше', 'какой округ', 'в каком округ', 'салыстыр')
ITEM_WORDS = ('ттх', 'характеристик', 'что такое', 'карточк', 'параметр', 'расход топлива', 'запас хода', 'экипаж')
LIST_WORDS = ('какие округ', 'список округ', 'перечисли округ', 'доступные округ', 'округа есть')
STOP = {'ттх', 'характеристики', 'характеристика', 'что', 'такое', 'карточка', 'карточку', 'покажи', 'дай', 'какие', 'какая',
        'какой', 'у', 'по', 'про', 'для', 'образца', 'образец', 'параметры', 'расход', 'топлива', 'запас', 'хода', 'экипаж', 'и', 'в'}


class KeywordPlanner:
    mode = 'ключевые слова'

    def __init__(self):
        self.fallback = None      # округ, подставленный без упоминания в вопросе

    def plan(self, question, districts):
        q = question.casefold()
        mentioned = self._districts(q, districts)
        metrics = [m for m, words in METRIC_WORDS.items() if any(w in q for w in words)]
        if any(w in q for w in LIST_WORDS):
            return [('list_districts', {})]
        if any(w in q for w in ITEM_WORDS):
            text = ' '.join(w for w in re.findall(r'[\w\-,.]+', question) if w.casefold() not in STOP)
            if text:
                return [('item_card', {'item': text})]
        if metrics and (any(w in q for w in COMPARE_WORDS) or (not mentioned and len(districts) > 1)):
            return [('compare_districts', {'metric': metrics[0]})]
        if not mentioned and len(districts) == 1:
            mentioned = [districts[0]['district_code']]
            self.fallback = districts[0]['short_name']
        calls = []
        for code in mentioned[:3]:
            if not metrics:
                calls.append(('district_summary', {'district': code}))
            for m in metrics[:2]:
                if m == 'personnel':
                    calls.append(('district_summary', {'district': code}))
                elif m == 'equipment':
                    calls.append(('district_equipment', {'district': code}))
                elif m == 'supply':
                    only = any(w in q for w in ('дефицит', 'нехват', 'не хватает'))
                    calls.append(('district_supply', {'district': code, 'only_deficit': True} if only else {'district': code}))
                else:
                    calls.append(('district_formations', {'district': code}))
        return calls

    @staticmethod
    def _districts(q, districts):
        """Округа, названные в вопросе: по коду (окр-аст, аст) или по форме слова (астаны, на востоке, юге).
        Слово должно начинаться с основы названия и отличаться окончанием не больше чем на 2 буквы:
        «запасов» не совпадает с «запад»."""
        words = re.findall(r'\w+', q)
        found = []
        for d in districts:
            code = d['district_code'].casefold()                       # окр-аст
            name = re.sub(r'[«»"]', '', d['short_name'].casefold())
            name = re.sub(r'^(округ|уч\.)\s+', '', name).strip()           # астана
            stem = name[:-1] if name[-1:] in 'аеёиоуыэюяь' and len(name) > 3 else name   # астан, восток, юг
            by_word = any(w.startswith(stem) and len(w) - len(stem) <= 2 for w in words)
            if code in q or code.split('-')[-1] in words or by_word:
                found.append(d['district_code'])
        return found

    def compose(self, question, results):
        if not results:
            return ('Не понял вопрос. Назовите округ и показатель, например: «Численность округа «Астана»», '
                    '«Сравни округа по технике», «Дефицит запасов на Востоке», «ТТХ БМП-2».')
        text = 'Найдено по вашему вопросу: ' + '; '.join(r['title'] for r in results) + '.'
        if self.fallback:
            text = (f'Округ в вопросе не распознан или вам недоступен; показан ваш единственный доступный округ — '
                    f'{self.fallback}. ' + text)
        return text
