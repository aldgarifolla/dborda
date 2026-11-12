#!/usr/bin/env bash
# Сравнение содержимого таблиц двух баз. Только чтение.
#   compare_db.sh "<psql-команда эталона>" "<psql-команда проверяемой>" [схема ...]
# Пример: compare_db.sh "docker exec -i db psql -U postgres -d military_lab" \
#                       "docker exec -i tmp psql -U postgres -d zz_build_check" mil_core refdata
# Для каждой таблицы эталона берётся её список колонок (по порядку), по этим же колонкам
# считается число строк и md5 от отсортированных md5 строк в обеих базах. Лишние колонки
# проверяемой базы (например load_run_id) в сравнение не входят. Часовой пояс сеанса
# фиксируется (UTC), иначе текст timestamptz зависел бы от настроек базы.
set -euo pipefail
A="$1"; B="$2"; shift 2; SCHEMAS=("${@:-mil_core}")
list=$(printf "'%s'," "${SCHEMAS[@]}"); list=${list%,}
tables=$($A -At -F'|' -c "select n.nspname, c.relname, string_agg(quote_ident(a.attname), ',' order by a.attnum)
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  join pg_attribute a on a.attrelid=c.oid and a.attnum>0 and not a.attisdropped
  where c.relkind='r' and n.nspname in ($list) group by 1,2 order by 1,2" </dev/null)
printf '%-34s %9s %9s  %s\n' table rows_ref rows_new result
bad=0
while IFS='|' read -r sch tbl cols; do
  q="set timezone='UTC'; select count(*)||'|'||coalesce(md5(string_agg(h,'' order by h)),'-') from (select md5(row($cols)::text) h from \"$sch\".\"$tbl\") x"
  ra=$($A -At -c "$q" </dev/null | tail -1); rb=$( ($B -At -c "$q" </dev/null 2>/dev/null || echo "?|missing") | tail -1)
  if [ "$ra" = "$rb" ]; then res=same; else res=DIFF; bad=$((bad+1)); fi
  printf '%-34s %9s %9s  %s\n' "$sch.$tbl" "${ra%%|*}" "${rb%%|*}" "$res"
done <<< "$tables"
echo "tables differing: $bad"
