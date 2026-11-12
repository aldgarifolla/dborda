"""Минимальная прослойка psycopg2 поверх psycopg 3.

Скрипты сборки (enrich.py, kz_localize.py) написаны под psycopg2. В образе web этого
проекта установлен только psycopg 3, а новые зависимости мы не добавляем. Прослойка даёт
ровно то, чем пользуются скрипты: connect(), cursor(), execute(), fetchall(), commit()
и extras.execute_values(). Подстановка параметров выполняется на стороне клиента
(psycopg.ClientCursor), как в psycopg2; кортеж Python превращается в список для IN (...).
"""
import psycopg
from psycopg import sql
from psycopg.adapt import Dumper


class _TupleAsInList(Dumper):
    def dump(self, obj):
        raise NotImplementedError('кортеж поддерживается только при подстановке на стороне клиента')

    def quote(self, obj):
        return b'(' + b','.join(sql.Literal(x).as_bytes(self.connection) for x in obj) + b')'


def connect(dsn):
    con = psycopg.connect(dsn, cursor_factory=psycopg.ClientCursor)
    con.adapters.register_dumper(tuple, _TupleAsInList)
    return con
