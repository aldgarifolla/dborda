# Django — веб-интерфейс к учебной PostgreSQL-базе

Это **дополнение** к уже запущенному `postgres_military_demo_full`, а не новая база. Существующий PostgreSQL остаётся на `127.0.0.1:5437`; сайт появится на `http://127.0.0.1:8001`.

## Установка в существующий проект (macOS + VS Code)

1. Скачайте `military_django_addon.zip` и распакуйте **содержимое архива в папку** `~/Downloads/postgres_military_demo_full`. Должны появиться `web/`, `compose.web.yaml`, `README_WEB.md`, новые файлы в `scripts/`. **Не удаляйте** существующие `init/`, `.env`, `compose.yaml`, Docker volume или проект VS Code.
2. Откройте в VS Code терминал в `postgres_military_demo_full` и выполните:

```bash
bash scripts/start_web.sh
```

3. Команда создаёт `.env.web`, а также отдельную БД `registry_auth` внутри уже запущенного PostgreSQL. Она собирает контейнер Django и выводит **новые случайные пароли** `demo_manager` / `demo_viewer` (при первом запуске). Сохраните пароли локально; не отправляйте их в чат.
4. Откройте **http://127.0.0.1:8001** и войдите под `demo_manager`.
5. Проверьте «Обзор», «Подразделения», карточку подразделения, «Каталог имущества», «Excel-модели», «Помощник» и «Права доступа».

### Если запускаете вручную

```bash
python3 scripts/create_web_env.py
bash scripts/init_web_auth.sh
docker compose -f compose.yaml -f compose.web.yaml up -d --build web
docker compose -f compose.yaml -f compose.web.yaml exec -T web python manage.py seed_demo
```

### Диагностика

```bash
docker compose -f compose.yaml -f compose.web.yaml ps
docker compose -f compose.yaml -f compose.web.yaml logs --tail=70 web
docker compose -f compose.yaml -f compose.web.yaml exec -T web python manage.py check
```

### Тесты (без обращения к военной базе)

```bash
docker compose -f compose.yaml -f compose.web.yaml exec -T web sh -lc 'DJANGO_TEST_SQLITE=1 python manage.py test catalog.tests --verbosity 2'
```

## ИИ-помощник на локальной модели

Модель работает на этом Mac через Ollama, бесплатно и без интернета; вопросы никуда не отправляются. Сайт обращается к ней по адресу `host.docker.internal:11434`.

```bash
brew install ollama
brew services start ollama
ollama pull qwen2.5:14b
```

Как это работает: модель получает вопрос, список доступных пользователю округов и описания инструментов (`web/catalog/assistant/tools.py`). Она выбирает инструмент, Django проверяет права и выполняет заранее написанный запрос, затем модель пишет короткий ответ только по полученным таблицам. SQL и схему базы модель не видит. Каждый вопрос пишется в журнал `AssistantAudit`.

Настройки (переменные окружения сервиса `web`):

- `ASSISTANT_PROVIDER` — `catalog.assistant.ollama.OllamaPlanner` (по умолчанию) или пусто для режима ключевых слов;
- `OLLAMA_MODEL` — другая модель Ollama с поддержкой инструментов, например `qwen2.5:3b` (быстрее, слабее);
- `OLLAMA_URL`, `OLLAMA_TIMEOUT` — адрес Ollama и таймаут в секундах.

### Облачные модели

- **Claude (Anthropic):** в `.env` — `ASSISTANT_PROVIDER=catalog.assistant.claude.ClaudePlanner`, в `.env.web` — `ANTHROPIC_API_KEY=...`; модель по умолчанию `claude-haiku-5-5`, другая — `CLAUDE_MODEL=claude-sonnet-5-5` в `.env.web`.
- **Groq, Gemini, OpenAI, xAI, Mistral, Alibaba** (OpenAI-совместимый API): в `.env` — `ASSISTANT_PROVIDER=catalog.assistant.openai_compat.OpenAICompatPlanner`, в `.env.web` — `LLM_PROVIDER`, `LLM_MODEL` и ключ провайдера (`GROQ_API_KEY`, `GEMINI_API_KEY` и т. д.).
- Вернуться на локальную модель — удалить строку `ASSISTANT_PROVIDER` из `.env`. После любой смены: `docker compose -f compose.yaml -f compose.web.yaml up -d --no-deps --force-recreate web`.
- Помощник устроен как чат: слева под «Помощником» — «Новый чат» и список чатов пользователя, внутри — лента сообщений и поле ввода (Enter — отправить). Чаты хранятся в `registry_auth` (таблицы `catalog_assistantchat`, `catalog_assistantmessage`), у каждого пользователя свои. Помощник видит 3 прошлых обмена чата и понимает уточнения («а на Востоке?»); число задаётся `CHAT_CONTEXT` в `web/catalog/views.py`, `0` — без истории (дешевле: уточнение стоит ≈ $0,3–0,4 за 1 000 против ≈ $0,16 у вопроса без истории).
- Помощник отвечает на языке вопроса: русском, казахском или английском. Коды латиницей (YUG-3, VOS-1) понимаются как ЮГ-3, ВОС-1. Ответ не на том языке и фразы вроде «отвечаю по-русски» модель переписывает.
- Сравнение моделей на 30 вопросах (русский, казахский, английский) с проверенными ответами: `python manage.py compare_models anthropic:claude-haiku-5-5 ollama:qwen2.5:14b` (отчёт в `web/reports/`).

Если Ollama выключена или не отвечает, страница не падает: помощник переключается на ключевые слова, это видно в строке «Режим».

## Что входит

- Django 5.2 / Python 3.12 / Django Templates, без React.
- Отдельная база `registry_auth` для пользователей, сессий, `UserRole`, `UnitGrant`, `GrantAudit`. Не использует межбазовые foreign keys.
- Read-only подключение `registry_reader` к `military_lab` через `registry_api`.
- Учебные пользователи: `demo_manager`, `demo_viewer`. `viewer` видит только разрешённый корень и его потомков; `manager` может выдавать разрешения другим viewer **только внутри собственной области**.
- Карточки подразделений с отдельным и агрегированным расчётом, списком штатных позиций и записями имущества.
- Excel-модели отдельно от основных данных, без повторного суммирования.
- Помощник на локальной языковой модели (Ollama, по умолчанию `qwen2.5:14b`; на слабом компьютере — `qwen2.5:7b`) без внешнего API и без доступа к произвольному SQL. Если модель не запущена, работает разбор по ключевым словам.

**Текущие ограничения:** учётные записи создаются только через команду администратора; публичной регистрации нет. Правила доступа реализованы в Django, а PostgreSQL роль `registry_reader` имеет доступ к read-only представлениям без индивидуальной фильтрации. Эту архитектуру нельзя считать готовой к размещению реальных чувствительных данных без отдельного security review, дополнительной изоляции, защиты сетевого соединения, production-развёртывания и проверки всех API. Представления не раскрывают персональные и медицинские карточки: отображаются только модельные связи с людьми. Количества показывают параметры **синтетической модели**.

**Не выполнять `docker compose down -v`**: так можно удалить локальный Docker volume с данными. Не копировать `.env` и `.env.web` в публичный репозиторий. `runserver` и `DEBUG=1` предназначены только для локального учебного стенда.
