"""Планировщик на облачной модели через OpenAI-совместимый API.

Один модуль для провайдеров с одинаковым форматом запросов /chat/completions и вызовом инструментов:
Groq, Google Gemini, OpenAI, xAI Grok, Mistral, Alibaba Cloud (Qwen). Промпты, инструменты, проверка прав
и запасные режимы — те же, что у локальной модели (ollama.py); отличается только транспорт.

Настройки (переменные окружения сервиса web, ключи — только в .env.web, не в коде и не в чате):
  ASSISTANT_PROVIDER=catalog.assistant.openai_compat.OpenAICompatPlanner
  LLM_PROVIDER=groq | gemini | openai | xai | mistral | qwen
  LLM_MODEL=<название модели у провайдера>
  <PROVIDER>_API_KEY=<ключ>, например GROQ_API_KEY
"""
import json
import os
import urllib.error
import urllib.request

from django.conf import settings

from .ollama import ModelUnavailable, OllamaPlanner, _ollama_tools

# Адреса OpenAI-совместимых API и имя переменной с ключом. Проверено по документации провайдеров;
# если провайдер сменит адрес, его можно переопределить переменной LLM_BASE_URL.
PROVIDERS = {
    'groq':    ('https://api.groq.com/openai/v1', 'GROQ_API_KEY'),
    'gemini':  ('https://generativelanguage.googleapis.com/v1beta/openai', 'GEMINI_API_KEY'),
    'openai':  ('https://api.openai.com/v1', 'OPENAI_API_KEY'),
    'xai':     ('https://api.x.ai/v1', 'XAI_API_KEY'),
    'mistral': ('https://api.mistral.ai/v1', 'MISTRAL_API_KEY'),
    'qwen':    ('https://dashscope-intl.aliyuncs.com/compatible-mode/v1', 'DASHSCOPE_API_KEY'),
}


class OpenAICompatPlanner(OllamaPlanner):
    def __init__(self, provider=None, model=None):
        super().__init__()
        self.provider = (provider or getattr(settings, 'LLM_PROVIDER', '') or 'groq').lower()
        if self.provider not in PROVIDERS:
            raise ModelUnavailable(f'неизвестный провайдер {self.provider}')
        base_url, key_var = PROVIDERS[self.provider]
        self.url = (os.environ.get('LLM_BASE_URL') or base_url).rstrip('/')
        self.api_key = os.environ.get(key_var, '')
        self.model = model or getattr(settings, 'LLM_MODEL', '')
        if not self.api_key:
            raise ModelUnavailable(f'не задан ключ {key_var} в .env.web')
        if not self.model:
            raise ModelUnavailable('не задана модель LLM_MODEL')
        self.mode = f'ИИ · {self.model} ({self.provider}, облако)'

    def _chat(self, messages, with_tools):
        body = {'model': self.model, 'messages': messages, 'temperature': 0.1}
        if with_tools:
            body['tools'] = _ollama_tools()          # тот же формат {'type': 'function', 'function': {...}}
            body['tool_choice'] = 'auto'
        req = urllib.request.Request(f'{self.url}/chat/completions', data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json',
                                              'Authorization': f'Bearer {self.api_key}'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:      # 401 — ключ, 429 — лимит, 400 — неверный запрос
            detail = exc.read()[:300].decode('utf-8', 'replace')
            raise ModelUnavailable(f'HTTP {exc.code}: {detail}') from exc
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise ModelUnavailable(str(exc)) from exc
        try:
            message = data['choices'][0]['message']
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelUnavailable(f'неожиданный ответ: {str(data)[:200]}') from exc
        # дальше общий код: tool_calls[].function.arguments — строка JSON, её разбирает _clean_args
        return {'content': message.get('content') or '', 'tool_calls': message.get('tool_calls') or []}
