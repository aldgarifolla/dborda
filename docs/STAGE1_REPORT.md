# Этап 1. Фиксация базы и происхождение данных

Дата: 2026-11-12. Стенд: `postgres_military_demo_full` (синтетические данные, PostgreSQL 16.15, Django 5.2).

## Итог в трёх строках

- Проект под git, секреты исключены, есть проверенная резервная копия обеих баз, 9 из 9 тестов проходят.
- Расхождения с журналом ETL объяснены: после загрузки данные меняли скрипты `enrich.py` и `kz_localize.py`, которые в журнал не пишут.
- Точный архив, из которого собран `init/10_full.sql`, на диске не найден; `SOURCE_MANIFEST.json` подтверждается только частично.

## 1. Что сделано

### Шаг 1. Git и секреты

- `.gitignore` дополнен: `.env.*` (кроме `.env.example`), `*.pyc`, `.idea/`, `*.dump`.
- Репозиторий инициализирован, ветка `main`, первый коммит `ded8c92`: 50 файлов, включая дампы `init/*.sql` (20 МБ, в `.git` 3,2 МБ).
- Проверено поиском по индексу: ни одно из четырёх значений из `.env` и `.env.web` в коммит не попало.
- Удалённого сервера нет, push не выполнялся.

### Шаг 2. Резервная копия

Папка `~/Backups/military_demo_full/2026-11-12/` (вне репозитория, права 700/600):

| Файл | Размер | SHA-256 |
|---|---|---|
| `military_lab.dump` | 2 439 680 | `f385ca3b926d621ea003f7c5ef8aa67cb3c5bdede71f978b4bdd7fb7b0a84652` |
| `registry_auth.dump` | 36 401 | `84f09dcb923d34738727a36bc054b83a5e327ecf48490f55e9ed7543d2a612f8` |
| `roles.sql` | 915 | `576afc03c5a20f4f47e8a3cefba953a21a08dcf20cee1614840c40c5ea4c9c03` |

- Дампы в формате custom, `roles.sql` снят с `--no-role-passwords` (хешей паролей в нём нет).
- Восстановление проверено во временных базах `zz_restore_check_lab` и `zz_restore_check_auth`:
  - `scripts/validate.sql` на копии прошёл (957 / 6993 / 6993 / 1631 / 155859 / 54 / 7982, права `registry_reader` те же);
  - число строк совпало по каждой таблице: `military_lab` 37 таблиц, 234 103 строки; `registry_auth` 12 таблиц, 64 строки;
  - совпало число представлений, функций, ограничений, индексов, последовательностей и прав;
  - контрольные суммы содержимого сверены для `unit`, `person`, `staff_position`, `vehicle`, `workbook_row`. Остальные таблицы сравнивались только по числу строк.
- Временные базы удалены, рабочие не менялись.

Восстановление на чистый сервер: сначала `roles.sql` и пароли ролей из `.env`, затем `pg_restore` обоих дампов.

### Шаг 3. Тесты

Команда из `README_WEB.md:38`. Результат: `Ran 9 tests in 4.823s — OK`, упавших и ошибок нет.

Тесты идут на SQLite в памяти; строка `Skipping setup of unused database(s): military` показывает, что к PostgreSQL они не обращаются. SQL из `web/catalog/repository.py` тестами не покрыт.

### Шаг 4. Происхождение данных

Расположение исходников:

- `~/Desktop/Military Dept/2 участник/`: `military_db_v2.db`, `military_db_v2_dump.sql`, `import_excel.py`.
- `~/Downloads/mil_excel_etl/`: `import_mil.py`, входные Excel, `out/mil_db_postgres.sql`.
- `~/Downloads/military_full.zip` (сборка 29 октября) и `~/Downloads/military_full (1).zip` (более поздняя сборка).

`import_excel.py` к проекту не относится: он грузит в схему `excel_core`, которой в `military_lab` нет.

#### Цепочка сборки

| Этап | Чем | Результат | Подтверждение |
|---|---|---|---|
| 1 | `import_mil.py` читает `brigade_все_данные.xlsx` и `military_db_v2_обзор.xlsx` | `mil_db_postgres.sql`: person 3518, item 307, rank 22 | хеш совпал с манифестом; числа совпали с `etl.load_run` |
| 2 | `schema_enrich.sql`, `enrich.py`, `functions.sql` | person 6993, item 327, rank 22 | сборка 29 октября в `military_full.zip` |
| 3 | `kz_localize.py` | rank 24, РФ → РК, казахские ФИО | таблица `rank` в `init/10_full.sql` совпадает с результатом скрипта |
| 4 | ручные вызовы функций в живой базе | +1 заявка, +2 складских движения | сравнение с дампом 29 октября |

Файл `military_db_v2.db` в сборке напрямую не участвует: `import_mil.py` читает Excel. То, что Excel-выгрузка сделана из этого `.db`, не доказано; числа согласуются.

#### Ответы на вопросы

- **person 6993 при 3518 в журнале.** `enrich.py:77-94` создаёт вымышленного человека на каждую штатную позицию без человека. В базе 3518 человек в подразделениях «свои» (id 6359–9876) и 3475 в подразделениях «противник» (id 9877–13351).
- **item 327 при 307.** `enrich.py:29-53` добавляет 20 позиций: топливо и масла, продовольствие, медицинское имущество, палатки, печь, канистра. Все 20 есть в базе.
- **rank 24 при 22.** `kz_localize.py:192-219` удаляет три российских звания и добавляет пять сержантских по закону РК: 22 − 3 + 5 = 24.
- **ФИО.** `kz_localize.py` заменил ФИО всех 3518 «своих». Имена в базе сгенерированы, а не взяты из Excel.
- **Следы ручной работы.** В `init/10_full.sql` есть заявка № 4 от «ассистент» (2026-10-29 12:52), заявка № 2 в статусе «выполнена» и два складских движения по ней. В скриптах сборки этого нет.

#### Сопоставление SQLite и `mil_core`

| SQLite (строк) | mil_core (строк) | Изменения |
|---|---|---|
| `tunion_structure` (957) | `unit` (957) | `structure_code` → `unit_code`, `parent_id` → `parent_code`, `sname` → `short_name`, `level_detail_united_id` → `level_name`; потеряны `source_id`, `faset_code`, `level_num`; страна РФ → РК |
| `tmilitary_unit` (442), `tforeign_unit` (383) | нет | численность в `unit.personnel_own`; `source_id`, `confidence` потеряны |
| `tstaff_position` (6993) | `staff_position` (6993) | потеряны `source_id`, `confidence` (A 2995, B 480, C 3518) |
| `tcl_personality_united` (3518) | `person` (6993) | поля ФИО переименованы; `birth_date` в `person_profile`; ФИО заменены |
| `tcl_rank` (27) | `rank` (24) | 27 → 22 в ETL (США 13 → 8), затем 22 → 24 |
| `tcl_position` (267) | `position` (267) | потеряна `staff_category` |
| `tprovide_el_united` (307), `tcl_provide_category` (12) | `item` (327) | категория текстом; `provide_el_united_id` → `legacy_id` |
| `tunion_structure_el_provide` (880) | `holding` (883) | потеряны `source_id`, `confidence`, `note`; добавлен `derived_from` |
| `tvvt_spec_fact` (330) | `item_spec` (370) | `source_id` → `source_code`; `confidence` сохранён; +40 строк из `enrich.py` |
| `tvvt_ammo_load` (27) | `vehicle_ammo_load` (27) | `confidence` сохранён; `source_id`, `note` потеряны |
| `tvvt_crew_role` (43), `tcrew_assignment` (3502) | `vehicle_crew_role`, `crew_assignment` | числа совпадают |
| `tkit` (35), `tkit_item` (108), `tposition_kit` (1308) | `kit`, `kit_item`, `position_kit` | у `tkit` потерян `source_id` |
| `tsource` (35), `tcl_param` (23) | `source` (35), `param` (24) | `accessed` → `accessed_on`; +1 параметр (`enrich.py:62`) |
| `tcountry` (269), `tds_sipri_milex` (8496) | `country` (228), `milex` (8496) | ключ `country_id` → `country_en` |
| `tds_armed_forces` (5746) | `country_forces` (221) | один год на страну |
| `tcl_level_detail_united` (48) | `unit_level` (46) | 2 дубля отброшены (`etl.reject`) |

Не перенесены: `tds_cow_nmc`, `tds_milex_gdp_longrun`, `tsource_total`, `tmandate_create`, `tcl_icons`, `tpersonality_photo`, `tmeta_table`, `tmeta_column`, `tcl_confidence`.

Появились только в PostgreSQL (сгенерированы `enrich.py`): `person_profile`, `person_vaccination`, `person_issue`, `vehicle`, `unit_property`, `warehouse`, `stock_norm`, `stock_movement`, `supply_request`, `item_alias`.

#### Проверка `SOURCE_MANIFEST.json`

| Запись | Результат |
|---|---|
| `mil_db_postgres.sql` | совпадает |
| `military_db_v2.db` | совпадает |
| `military_db_v2_dump.sql` | совпадает |
| `military_db_v2_обзор.xlsx` | совпадает |
| `demo_sql_sha256` | совпадает с `init/25_full_workbook_demo.sql` |
| `military_full (1).zip` | не совпадает: в манифесте 4 368 163 байта, на диске 3 871 833 и другой хеш |
| `military_full_обзор.xlsx` | не совпадает ни с одним из двух найденных файлов |
| `Штатные_должности_численность_имущество_2026.xlsx` | файл не найден |
| `built_from` | не подтверждается |

Файл `military_full (1).zip` на диске изменён 2026-11-12 и содержит другую сборку (unit 803, person 6007, добавлен `training_mask.py`). `init/10_full.sql` не совпадает ни с ним, ни со сборкой 29 октября. Хешей `init/10_full.sql` и `init/20_reference_and_safe_views.sql` в манифесте нет.

Хеши на момент проверки:

| Файл | SHA-256 |
|---|---|
| `init/10_full.sql` | `fa62ae10246026a47aaba6a1db4ef2e9877737b2507902202a170f43d8d546e4` |
| `init/20_reference_and_safe_views.sql` | `a90e124ffc7244c9c2375188eb66b633fd08f2fbfb57cfc0a0baa41ffab61aed` |
| `init/25_full_workbook_demo.sql` | `2d9f118bb18078ad5724bea12512ff2fb9478122f16ec6cb28b5720845a4a6cc` |

#### Источник и достоверность по таблицам

| Состояние | Таблицы |
|---|---|
| Есть источник и достоверность | `item_spec` |
| Есть только достоверность | `unit` (A 705, C 252; значения B не было и в SQLite), `vehicle_ammo_load` |
| Было в SQLite, потеряно при импорте | `staff_position`, `holding`, `kit`, численность подразделений |
| Сгенерировано скриптами | `person`, `person_profile`, `person_vaccination`, `person_issue`, `vehicle`, `unit_property`, `warehouse`, `stock_norm`, `stock_movement`, `supply_request`, `item_alias`, 20 строк `item`, 40 строк `item_spec` |
| Справочники без пометок | `rank`, `position`, `unit_level`, `param`, `country`, `milex`, `country_forces`, `position_kit`, `kit_item`, `vehicle_crew_role`, `crew_assignment` |

Ни в одной таблице `mil_core` нет ссылки на `etl.load_run.run_id`: строку нельзя привязать к загрузке.

## 2. Что не удалось или не проверено

- Не найден архив, из которого собран `init/10_full.sql`, и файл `Штатные_должности_численность_имущество_2026.xlsx`. Поэтому не проверено происхождение `init/25_full_workbook_demo.sql` и `refdata`.
- Не доказано, что `military_db_v2_обзор.xlsx` выгружен из `military_db_v2.db`.
- Не объяснены расхождения 880 → 883 (`holding`) и 269 → 228 (`country`).
- Сопоставление SQLite и `mil_core` сделано по структуре и числу строк, значения построчно не сверялись.
- Архив `military_demo_upgrade_ai.zip` не вскрывался.
- Версия `kz_localize.py`, применённая к базе, неизвестна: проверено только совпадение таблицы `rank` с результатом версии из `military_full (1).zip`.

## 3. Найденные расхождения

1. Журнал `etl.load_run` описывает одну загрузку из четырёх этапов сборки; этапы 2–4 нигде не зафиксированы.
2. `SOURCE_MANIFEST.json`: три записи из восьми не подтверждаются, `built_from` указывает на файл, которого нет.
3. Имя `military_full (1).zip` на диске занято другой сборкой, отличной от указанной в манифесте.
4. В базовом дампе остались результаты ручных действий (заявка, складские движения).
5. Уровень достоверности и источник, которые были в SQLite у штата, имущества подразделений и численности, при импорте отброшены.
6. 3475 человек «противника» и все ФИО «своих» сгенерированы, но в данных это никак не помечено.

## 4. Рекомендация по этапу 2

Цель: каждая строка должна отвечать на вопросы «откуда», «насколько достоверно» и «какой загрузкой внесена».

1. **Воспроизводимая сборка.** Положить в репозиторий скрипты всех этапов (`import_mil.py`, `schema_enrich.sql`, `enrich.py`, `functions.sql`, `kz_localize.py`) в той версии, которая даёт текущую базу, и один сценарий сборки. Критерий: сборка с нуля даёт те же счётчики, что `validate.sql`.
2. **Журнал для каждого этапа.** Каждый скрипт пишет запись в `etl.load_run`: имя и хеш скрипта, хеши входных файлов, время, счётчики до и после. Ручные изменения запрещены или идут через тот же журнал.
3. **Версия данных на строке.** Добавить в таблицы `mil_core` поля `load_run_id` и признак происхождения строки: импорт, расчёт, генерация.
4. **Вернуть источник и достоверность.** Перенести `source_id` и `confidence` из SQLite/Excel в `staff_position`, `holding`, `kit` и численность подразделений; сгенерированным строкам ставить явную пометку.
5. **Исправить манифест.** Пересчитать хеши по реальным файлам, добавить хеши `init/10_full.sql` и `init/20_…sql`, убрать или заменить записи о ненайденных файлах, исправить `built_from`.
6. **Чистый базовый дамп.** Убрать из него следы ручных действий либо оформить их как отдельный шаг с записью в журнале.
7. **Тест на реальном SQL.** Хотя бы один тест, выполняющий запросы `repository.py` на PostgreSQL, и запуск `validate.sql` после каждой сборки.

До начала этапа 2 нужно решение по двум вопросам: какую версию `military_full` считать исходной (29 октября плюс `kz_localize.py` или новую сборку с `training_mask.py`) и где взять файл `Штатные_должности_численность_имущество_2026.xlsx`.
