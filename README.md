# Military PostgreSQL Lab — изолированный учебный экземпляр

**НЕ является актуальной базой ВС РК.** Сведения о 12 мбр, людях, машинах, складах и товарах в `military_full.sql` указаны авторами как вымышленные/условные. Достоверность и пригодность для эксплуатации не подтверждены.

## Что собрано

- Основная БД PostgreSQL 16: `military_lab`, импорт исходного `military_full.sql` без редактирования.
- `mil_core` — полный импорт учебного набора; `etl` и `excel_stage` — исходные журналы и staging.
- `refdata.reference_entry` — отдельно перенесены строки трёх **публичных справочных разделов** приложенного XLSX (без листов «Модель...»). Все записи помечены `verified_for_operational_use = false`; значения `NULL` не заполнены выдуманными числами.
- `registry_api` — read-only представления для начальной интеграции Django: `units`, `staff_positions`, `unit_staff_summary`, `items`, `holdings`, `sources`.
- `registry_reader` — пользователь PostgreSQL с доступом только к `registry_api` и `refdata` без допуска к исходным персональным и медицинским записям, и без EXECUTE над функциями `fn_*`.

## Запуск на macOS с Docker Desktop

**Эта сборка использует отдельный проект Docker `military-demo-full` и порт `5437`, не затрагивая предыдущий `military-research-lab` на `5436`.**


1. Распакуй архив, открой папку `postgres_military_lab` в PyCharm.
2. Docker Desktop должен быть запущен.
3. Во встроенном терминале PyCharm:

```bash
python3 scripts/make_env.py
docker compose up -d
docker compose logs --tail=80 db
bash scripts/check.sh
```

**Важно:** начальная загрузка 12 МБ SQL выполняется лишь для **пустого** Docker volume. Когда она завершится, проверка выведет ожидаемые числа и подтверждения привилегий. `pg_isready` может стать зелёным чуть раньше завершения импорта; при ошибке смотрите `docker compose logs db`.

PyCharm → Database → Add Data Source → PostgreSQL:
- Host: `127.0.0.1`
- Port: `5437`
- Database: `military_lab`
- User: `registry_reader`
- Password: строка `APP_READER_PASSWORD` из локального `.env`.

Для администратора: `postgres` / пароль `POSTGRES_PASSWORD`; административный логин не использовать в Django или ИИ.

Пример SQL в PyCharm:
```sql
SELECT unit_code, short_name, level_name, data_status
FROM registry_api.units LIMIT 10;

SELECT unit_code, direct_model_staff_positions
FROM registry_api.unit_staff_summary LIMIT 10;

SELECT source_sheet, count(*)
FROM refdata.reference_entry
GROUP BY source_sheet;
```

Проверка не должна показывать персональные карточки через `registry_reader`. Полный `mil_core` открыт только администратору БД на учебном стенде.

### Если docker compose не стартует

Сначала выполнить `docker compose ps` и `docker compose logs db`. Не использовать `docker compose down -v` для сохранённых данных. Для полного удаления именно ЭТОЙ учебной БД, в отличие от простого выключения, нужно осознанное решение.

Остановить без удаления данных: `docker compose down`.

## Важно про Django и ИИ

- Текущий `registry_reader` — **разработческий** пользователь для безопасных представлений; он не обеспечивает разграничение по подразделениям. Прежде чем давать доступ реальным пользователям, внедрите Django grants + версии структуры + tests на агрегаты и обрезание областей.
- `mil_core` содержит вызываемые из SQL функции `fn_issue`, `fn_request_fulfil`, `fn_check_and_request`; это **изменяющие данные операции**. Полномочия на их вызов отозваны у PUBLIC. ИИ не получает произвольный SQL или пароль postgres.
- Смена схемы/данных в `military_full.sql` **не миграция**. Текущий compose загружает её на чистый volume при первом создании. Не подменяйте модель действующими данными без источника, утверждённого словаря показателей и проверки режима доступа.
- В режиме реальных чувствительных сведений требуется отдельный согласованный, изолированный сервер и дополнительное разграничение на уровне записей и полей. Не открывайте порт PostgreSQL наружу.

## Источники и проверяемость

`SOURCE_MANIFEST.json` содержит SHA-256 всех полученных файлов; `scripts/check_static.py` проверяет количество строк в SQL без запуска PostgreSQL. `scripts/check.sh` проверяет состояние после настоящего импорта и права ограниченной роли.

**Ограничение тестов:** в среде подготовки архива Docker/psql отсутствуют. Поэтому физическая загрузка PostgreSQL здесь не выполнялась; она подготовлена для запуска командой `docker compose up -d` на твоём Mac. Не считать проект рабочим сервером до успешного `bash scripts/check.sh`.
