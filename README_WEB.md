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

## Что входит

- Django 5.2 / Python 3.12 / Django Templates, без React.
- Отдельная база `registry_auth` для пользователей, сессий, `UserRole`, `UnitGrant`, `GrantAudit`. Не использует межбазовые foreign keys.
- Read-only подключение `registry_reader` к `military_lab` через `registry_api`.
- Учебные пользователи: `demo_manager`, `demo_viewer`. `viewer` видит только разрешённый корень и его потомков; `manager` может выдавать разрешения другим viewer **только внутри собственной области**.
- Карточки подразделений с отдельным и агрегированным расчётом, списком штатных позиций и записями имущества.
- Excel-модели отдельно от основных данных, без повторного суммирования.
- Rule-based помощник без внешнего API и без доступа к произвольному SQL.

**Текущие ограничения:** учётные записи создаются только через команду администратора; публичной регистрации нет. Правила доступа реализованы в Django, а PostgreSQL роль `registry_reader` имеет доступ к read-only представлениям без индивидуальной фильтрации. Эту архитектуру нельзя считать готовой к размещению реальных чувствительных данных без отдельного security review, дополнительной изоляции, защиты сетевого соединения, production-развёртывания и проверки всех API. Представления не раскрывают персональные и медицинские карточки: отображаются только модельные связи с людьми. Количества показывают параметры **синтетической модели**.

**Не выполнять `docker compose down -v`**: так можно удалить локальный Docker volume с данными. Не копировать `.env` и `.env.web` в публичный репозиторий. `runserver` и `DEBUG=1` предназначены только для локального учебного стенда.
