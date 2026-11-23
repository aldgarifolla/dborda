"""Планировщик на модели Claude (Anthropic) через официальную библиотеку anthropic.

Подключается настройками сервиса web:
  ASSISTANT_PROVIDER=catalog.assistant.claude.ClaudePlanner
  CLAUDE_MODEL=claude-haiku-5-5            (по умолчанию)
  ANTHROPIC_API_KEY=<ключ>                 (только в .env.web, не в коде и не в чате)

Промпты, инструменты, проверка прав и запасные режимы — общие с ollama.py; отличается только транспорт.
Инструкция кешируется (повторное чтение кеша в 10 раз дешевле обычного входа). Глубина рассуждений:
низкая при выборе инструментов (быстро и дёшево), средняя при написании ответа (без рассуждений вслух).
"""
import os

import anthropic
from django.conf import settings

from . import tools
from .ollama import ModelUnavailable, OllamaPlanner

# $ за 1 млн токенов (platform.claude.com/docs/en/about-claude/pricing, проверено 21.11.2026; промпт до 100 тыс.)
PRICES = {'claude-haiku-5-5': {'input': 0.10, 'output': 0.50, 'cache_write': 0.125, 'cache_read': 0.01}}


TITLE_PROMPT = ('Придумай короткое название для чата по первому вопросу пользователя: 2–4 слова, не длиннее 30 '
                'знаков, на языке вопроса. Только само название — без кавычек, точки в конце и пояснений. '
                'Для приветствия или постороннего вопроса — «Приветствие» или суть вопроса.')


def clean_title(text):
    """Название от модели без обрамляющих кавычек, точки и звёздочек. Кавычки внутри («Юг») сохраняются:
    «Численность округа «Юг»» -> Численность округа «Юг»."""
    text = str(text).strip().strip('*').strip().rstrip('.').strip()
    pairs = {'«': '»', '"': '"', "'": "'", '“': '”'}
    if text[:1] in pairs and text.endswith(pairs[text[0]]) and len(text) > 1:
        inner = text[1:-1].strip()
        # снимаем внешние кавычки, только если внутри после этого кавычки остаются парными
        if inner.count('«') == inner.count('»'):
            text = inner
    if text.count('«') > text.count('»'):
        text += '»'
    return text[:60].strip() or None


class ClaudePlanner(OllamaPlanner):
    def __init__(self, model=None):
        super().__init__()
        key = os.environ.get('ANTHROPIC_API_KEY', '')
        if not key:
            raise ModelUnavailable('не задан ключ ANTHROPIC_API_KEY в .env.web')
        self.model = model or getattr(settings, 'CLAUDE_MODEL', '') or 'claude-haiku-5-5'
        self.client = anthropic.Anthropic(api_key=key, timeout=self.timeout, max_retries=2)
        self.mode = f'ИИ · {self.model} (Anthropic)'   # не длиннее 40 знаков — поле журнала
        self.usage = {'input': 0, 'output': 0, 'cache_write': 0, 'cache_read': 0}

    def _chat(self, messages, with_tools):
        # первая запись — системная инструкция; остальные — диалог (в т. ч. поздние системные напоминания)
        system, rest = messages[0]['content'], messages[1:]
        request = {
            'model': self.model,
            'max_tokens': 4096,
            'system': [{'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}}],
            'messages': rest,
            # выбор инструмента — низкая глубина (быстро); ответ — средняя: на низкой модель рассуждает прямо в тексте
            'output_config': {'effort': 'low' if with_tools else 'medium'},
        }
        if with_tools:
            request['tools'] = tools.schemas()
            # Выбор инструмента не требует рассуждений: без них с историей чата модель «думает» лишние токены.
            # На Haiku 5.5 thinking можно отключить при effort не выше high (у нас low).
            request['thinking'] = {'type': 'disabled'}
        try:
            response = self.client.messages.create(**request)
        except anthropic.APIStatusError as exc:          # 401 ключ, 429 лимит, 529 перегрузка, 400 запрос
            raise ModelUnavailable(f'HTTP {exc.status_code}: {exc.message}') from exc
        except anthropic.APIConnectionError as exc:
            raise ModelUnavailable(f'нет соединения с Anthropic: {exc}') from exc
        self._count(response.usage)
        if response.stop_reason == 'refusal':
            raise ModelUnavailable('модель отказалась отвечать')
        text = ''.join(b.text for b in response.content if b.type == 'text').strip()
        calls = [{'function': {'name': b.name, 'arguments': b.input}}
                 for b in response.content if b.type == 'tool_use']
        return {'content': text, 'tool_calls': calls}

    def title(self, question, answer=''):
        """Короткое название чата (≈ 100 токенов на входе, ≈ 10 на выходе). None — если модель недоступна."""
        try:
            response = self.client.messages.create(
                model=self.model, max_tokens=40, system=TITLE_PROMPT,
                messages=[{'role': 'user', 'content': f'Вопрос: {question}\nОтвет: {str(answer)[:300]}'}],
                output_config={'effort': 'low'}, thinking={'type': 'disabled'})
        except (anthropic.APIStatusError, anthropic.APIConnectionError):
            return None
        self._count(response.usage)
        if response.stop_reason == 'refusal':
            return None
        text = ''.join(b.text for b in response.content if b.type == 'text').strip().split('\n')[0]
        return clean_title(text)

    def _count(self, usage):
        self.usage['input'] += usage.input_tokens or 0
        self.usage['output'] += usage.output_tokens or 0
        self.usage['cache_write'] += getattr(usage, 'cache_creation_input_tokens', 0) or 0
        self.usage['cache_read'] += getattr(usage, 'cache_read_input_tokens', 0) or 0

    def cost(self):
        """Стоимость накопленного расхода в $ по ценам PRICES (None, если цен модели нет)."""
        price = PRICES.get(self.model)
        if not price:
            return None
        return sum(self.usage[k] * price[k] for k in price) / 1_000_000
