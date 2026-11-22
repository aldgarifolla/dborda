"""Один вопрос -> план вызовов -> проверенные вызовы инструментов -> ответ и запись в журнал."""
from django.conf import settings
from django.utils.module_loading import import_string

from .. import repository as repo
from ..models import AssistantAudit
from . import tools
from .planner import KeywordPlanner

MAX_QUESTION = 500
MAX_CALLS = 4


def get_planner():
    """Провайдер из settings.ASSISTANT_PROVIDER (путь к классу). По умолчанию — ключевые слова."""
    path = getattr(settings, 'ASSISTANT_PROVIDER', '')
    if path:
        try:
            return import_string(path)()
        except Exception:                      # модель недоступна или не настроена — работаем без неё
            pass
    return KeywordPlanner()


def answer(user, scope, question, planner=None, audit=True, history=None):
    """planner — готовый планировщик (для сравнения моделей); audit=False — не писать в журнал;
    history — прошлые обмены чата [(вопрос, ответ), …], чтобы понимать уточнения («а на Востоке?»)."""
    question = (question or '').strip()[:MAX_QUESTION]
    result = {'question': question, 'text': '', 'tables': [], 'calls': [], 'mode': '', 'ok': True}
    if not question:
        result.update(text='Введите вопрос.', ok=False)
        return result
    if not scope:
        result.update(text='Вам не выдан доступ ни к одному учебному округу.', ok=False)
        return result
    districts = repo.list_districts(scope)
    planner = planner or get_planner()
    planner.history = list(history or [])
    try:
        calls = planner.plan(question, districts)
    except Exception:                          # сбой модели не должен ронять страницу
        planner = KeywordPlanner()
        calls = planner.plan(question, districts)
    result['mode'] = planner.mode
    for name, args in list(calls)[:MAX_CALLS]:
        entry = {'tool': name, 'args': args, 'ok': True}
        try:
            table = tools.run(name, args, scope)
            result['tables'].append(table)
            entry['source'] = table['source']
        except tools.ToolError as exc:
            entry.update(ok=False, error=str(exc))
            result['ok'] = False
        result['calls'].append(entry)
    errors = [c['error'] for c in result['calls'] if not c['ok']]
    result['text'] = ' '.join(errors) if errors and not result['tables'] else planner.compose(question, result['tables'])
    if audit:
        # длины — по полям журнала (mode 40, question 500): «ИИ · claude-haiku-5-5 (Anthropic, облако)» длиннее 40
        AssistantAudit.objects.create(user=user, question=question[:500], mode=result['mode'][:40], calls=result['calls'],
                                      answer=result['text'][:2000], ok=result['ok'])
    return result


def suggest_title(question, answer=''):
    """Короткое название чата от модели, если планировщик это умеет (Claude). Иначе None — останется обрезка."""
    planner = get_planner()
    make = getattr(planner, 'title', None)
    if not make:
        return None
    try:
        return make(question, answer)
    except Exception:                          # название — не повод ронять страницу
        return None
