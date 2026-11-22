"""Сравнение моделей помощника на одном наборе вопросов с проверенными ответами.

    python manage.py compare_models ollama:qwen2.5:14b groq:llama-3.3-70b-versatile gemini:gemini-2.5-flash
    python manage.py compare_models ollama:qwen2.5:7b --pause 3 --only 1,2,3
    python manage.py compare_models anthropic:claude-haiku-5-5 --group казахский

Модель задаётся как «провайдер:название». ollama — локальная, остальные — облако через OpenAI-совместимый API
(ключ берётся из .env.web). Каждый вопрос задаётся от имени пользователя из набора, с его правами доступа;
в журнал помощника вопросы не пишутся. Отчёт в Markdown сохраняется в web/reports/.
"""
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from catalog import repository as repo
from catalog.assistant import engine
from catalog.assistant.ollama import FOREIGN_SCRIPT, ModelUnavailable, META_SENTENCE, OllamaPlanner, language
from catalog.assistant.openai_compat import OpenAICompatPlanner

QUESTIONS = Path(__file__).resolve().parents[2] / 'assistant' / 'eval_questions.json'
REPORTS = Path(__file__).resolve().parents[3] / 'reports'


def make_planner(spec):
    provider, _, model = spec.partition(':')
    if not model:
        raise CommandError(f'«{spec}»: нужен формат провайдер:модель, например ollama:qwen2.5:14b')
    if provider == 'anthropic':
        from catalog.assistant.claude import ClaudePlanner
        try:
            return ClaudePlanner(model)
        except ModelUnavailable as exc:
            raise CommandError(f'{spec}: {exc}')
    if provider == 'ollama':
        planner = OllamaPlanner()
        planner.model = model
        planner.mode = f'ИИ · {model} (локально)'
        return planner
    try:
        return OpenAICompatPlanner(provider, model)
    except ModelUnavailable as exc:
        raise CommandError(f'{spec}: {exc}')


def verdict(item, result):
    text = result['text']
    if item.get('check') == 'manual':
        return 'manual'
    if result['mode'] == 'ключевые слова':
        return 'fail'                                   # модель не ответила, сработал запасной режим
    if FOREIGN_SCRIPT.search(text) or META_SENTENCE.search(text):
        return 'fail'                                   # чужой алфавит или рассуждения о языке вопроса
    if any(x in text for x in item.get('expect_none', [])):
        return 'fail'
    if item.get('expect_any') and not any(x in text for x in item['expect_any']):
        return 'fail'
    if item.get('answer_lang') and language(text.replace(item['q'], '')) != item['answer_lang']:
        return 'fail'                                   # ответ должен быть на языке вопроса
    return 'ok'


class Command(BaseCommand):
    help = 'Сравнить модели помощника на наборе вопросов с проверенными ответами'

    def add_arguments(self, parser):
        parser.add_argument('models', nargs='+', help='провайдер:модель, например ollama:qwen2.5:14b')
        parser.add_argument('--pause', type=float, default=0, help='пауза между вопросами, с (для бесплатных лимитов)')
        parser.add_argument('--only', default='', help='номера вопросов через запятую')
        parser.add_argument('--group', default='', help='только вопросы одной группы, например «казахский»')

    def handle(self, *args, models, pause, only, group, **opts):
        data = json.loads(QUESTIONS.read_text())
        items = data['questions']
        if only:
            wanted = {int(x) for x in only.split(',')}
            items = [q for q in items if q['id'] in wanted]
        if group:
            items = [q for q in items if q['group'] == group]
        users = {u.username: u for u in get_user_model().objects.filter(username__in={q['user'] for q in items})}
        scopes = {name: repo.allowed_codes(u) for name, u in users.items()}

        summary, details = [], []
        for spec in models:
            planner = make_planner(spec)
            self.stdout.write(f'\n##### {spec}')
            rows, times = [], []
            for item in items:
                user = users[item['user']]
                started = time.time()
                result = engine.answer(user, scopes[item['user']], item['q'], planner=planner, audit=False)
                spent = time.time() - started
                times.append(spent)
                v = verdict(item, result)
                calls = '; '.join(f'{c["tool"]}({json.dumps(c["args"], ensure_ascii=False)})'
                                  + ('' if c['ok'] else ' — отказ') for c in result['calls']) or '—'
                rows.append((item, v, spent, calls, result))
                mark = {'ok': 'OK ', 'fail': 'BAD', 'manual': '?  '}[v]
                self.stdout.write(f'{mark} {spent:5.1f}s #{item["id"]} {item["q"]}\n      {calls}\n      {result["text"][:200]}')
                if pause:
                    time.sleep(pause)
            auto = [r for r in rows if r[1] != 'manual']
            ok = sum(r[1] == 'ok' for r in auto)
            cost = planner.cost() if hasattr(planner, 'cost') else None
            per_1000 = f'${cost / len(rows) * 1000:.2f}' if cost is not None else '—'
            summary.append((spec, ok, len(auto), statistics.mean(times), statistics.median(times), max(times),
                            sum(r[4]['mode'] == 'ключевые слова' for r in rows), per_1000))
            if cost is not None:
                self.stdout.write(f'   токены: {planner.usage}; стоимость прогона ${cost:.4f}, ≈ {per_1000} за 1 000 вопросов')
            details.append((spec, rows))
            self.stdout.write(f'== {spec}: {ok}/{len(auto)} верно, среднее {statistics.mean(times):.1f} с')

        REPORTS.mkdir(exist_ok=True)
        path = REPORTS / f'compare_{datetime.now():%Y-%m-%d_%H%M}.md'
        path.write_text(self.render(summary, details), encoding='utf-8')
        self.stdout.write(f'\nОтчёт: web/reports/{path.name}')

    @staticmethod
    def render(summary, details):
        out = [f'# Сравнение моделей помощника — {datetime.now():%d.%m.%Y %H:%M}', '',
               'Вопросы и правильные ответы: `web/catalog/assistant/eval_questions.json`. Время — на весь вопрос '
               '(выбор инструментов, запрос к базе, ответ). «Запасной режим» — модель не ответила, сработали '
               'ключевые слова; такой ответ считается ошибкой.', '',
               '| Модель | Верно | Среднее, с | Медиана, с | Максимум, с | Запасной режим | ≈ $ за 1 000 вопросов |',
               '|---|---|---|---|---|---|---|']
        for spec, ok, total, mean, median, worst, fallback, per_1000 in summary:
            out.append(f'| {spec} | {ok}/{total} | {mean:.1f} | {median:.1f} | {worst:.1f} | {fallback} | {per_1000} |')
        for spec, rows in details:
            out += ['', f'## {spec}', '', '| # | Группа | Вопрос | Итог | Время, с | Инструменты | Ответ | Ожидалось |',
                    '|---|---|---|---|---|---|---|---|']
            for item, v, spent, calls, result in rows:
                text = result['text'].replace('|', '/').replace('\n', ' ')[:300]
                out.append(f'| {item["id"]} | {item["group"]} | {item["q"]} | '
                           f'{ {"ok": "верно", "fail": "ошибка", "manual": "вручную"}[v] } | {spent:.1f} | '
                           f'{calls.replace("|", "/")} | {text} | {item["answer"]} |')
        return '\n'.join(out) + '\n'
