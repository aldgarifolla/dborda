#!/usr/bin/env python3
from pathlib import Path
import re,hashlib,sys
base=Path(__file__).resolve().parents[1]
s=(base/'init'/'10_full.sql').read_text(encoding='utf-8')
expected={
 'mil_core.unit':957,
 'mil_core.staff_position':6993,
 'mil_core.person':6993,
 'mil_core.vehicle':1631,
 'mil_core.person_issue':155859
}
for t,n in expected.items():
 m=re.search(r'COPY '+re.escape(t)+r' \([^\n]+ FROM stdin;\n(.*?)\n\\\.',s,re.S)
 if not m:raise SystemExit('COPY missing '+t)
 got=len(m.group(1).splitlines())
 if got !=n:raise SystemExit(f'COUNT FAIL {t} {got} != {n}')
 print(f'{t}: {got} (static dump check)')
assert not re.search('SECURITY DEFINER|CREATE EXTENSION|CREATE ROLE',s,re.I)
print('Dump static checks OK. Live PostgreSQL validation is separate.')
