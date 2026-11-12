"""Сверка Excel-книги с refdata.workbook_row / refdata.reference_entry. Только чтение, только stdlib.

  python3 -I check_workbook.py <книга.xlsx> <workbook_rows.jsonl> [<reference_entries.jsonl>]

JSONL получают из базы запросами (см. build/README.md):
  select json_build_object('sheet',sheet_name,'row',source_row,'payload',payload) from refdata.workbook_row
  select json_build_object('sheet',source_sheet,'row',source_row,'payload',raw_fields) from refdata.reference_entry
Строка книги сопоставляется со строкой базы по ключу (лист, номер строки Excel).
Заголовок листа — первая строка, у которой заполнено не меньше трёх ячеек подряд и после
которой идут данные; определяется по списку колонок из базы, если он передан.
"""
import json, re, sys, zipfile
import xml.etree.ElementTree as ET

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'p': 'http://schemas.openxmlformats.org/package/2006/relationships'}


def col_index(ref):
    n = 0
    for ch in re.match(r'[A-Z]+', ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(path):
    z = zipfile.ZipFile(path)
    shared = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', NS):
            shared.append(''.join(t.text or '' for t in si.iter('{%s}t' % NS['m'])))
    rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels')).findall('p:Relationship', NS)}
    book = {}
    for s in ET.fromstring(z.read('xl/workbook.xml')).find('m:sheets', NS):
        target = rels[s.get('{%s}id' % NS['r'])]
        target = target.lstrip('/') if target.startswith('/') else 'xl/' + target
        rows = {}
        for row in ET.fromstring(z.read(target)).iter('{%s}row' % NS['m']):
            cells = {}
            for c in row.findall('m:c', NS):
                t, v = c.get('t'), c.find('m:v', NS)
                if t == 'inlineStr':
                    val = ''.join(x.text or '' for x in c.iter('{%s}t' % NS['m']))
                elif v is None or v.text is None:
                    continue
                elif t == 's':
                    val = shared[int(v.text)]
                elif t in ('str', 'e'):
                    val = v.text
                elif t == 'b':
                    val = v.text == '1'
                else:
                    f = float(v.text); val = int(f) if f == int(f) else f
                if val != '':
                    cells[col_index(c.get('r'))] = val
            if cells:
                rows[int(row.get('r'))] = cells
        book[s.get('name')] = rows
    return book


def norm(v):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return int(v) if float(v) == int(v) else round(float(v), 9)
    return str(v).strip()


def load(path):
    out = {}
    for line in open(path, encoding='utf-8'):
        if line.strip():
            d = json.loads(line); out[(d['sheet'], d['row'])] = d['payload']
    return out


def compare(book, db, label):
    print(f'== {label}')
    total_bad = 0
    for sheet in sorted({s for s, _ in db}):
        rows = book.get(sheet)
        dbrows = {r: p for (s, r), p in db.items() if s == sheet}
        if rows is None:
            print(f'{sheet}: листа нет в книге, строк в базе {len(dbrows)}'); total_bad += len(dbrows); continue
        keys = set().union(*[set(p) for p in dbrows.values()])
        header_row = next((r for r in sorted(rows) if keys and keys <= {str(v).strip() for v in rows[r].values()}), None)
        if header_row is None:
            print(f'{sheet}: не найдена строка заголовка'); total_bad += len(dbrows); continue
        header = {i: str(v).strip() for i, v in rows[header_row].items()}
        data = {r: {header[i]: norm(v) for i, v in c.items() if i in header} for r, c in rows.items() if r > header_row}
        same = diff = 0; examples = []
        for r, p in dbrows.items():
            x = data.get(r, {})
            pn = {k: norm(v) for k, v in p.items() if v is not None and v != ''}
            if x == pn:
                same += 1
            else:
                diff += 1
                if len(examples) < 2:
                    examples.append((r, {k: (x.get(k), pn.get(k)) for k in set(x) | set(pn) if x.get(k) != pn.get(k)}))
        only_book = sorted(set(data) - set(dbrows))
        print(f'{sheet}: заголовок в строке {header_row}; в книге {len(data)}, в базе {len(dbrows)}, '
              f'совпало {same}, отличается {diff}, только в книге {len(only_book)}')
        for e in examples:
            print('   пример отличия:', json.dumps(e, ensure_ascii=False)[:300])
        if only_book:
            print('   строки только в книге:', only_book[:10])
        total_bad += diff + len(only_book)
    print(f'итого расхождений: {total_bad}')
    return total_bad


if __name__ == '__main__':
    book = read_xlsx(sys.argv[1])
    print('листы книги:', {k: len(v) for k, v in book.items()})
    bad = compare(book, load(sys.argv[2]), 'refdata.workbook_row')
    if len(sys.argv) > 3:
        bad += compare(book, load(sys.argv[3]), 'refdata.reference_entry')
    sys.exit(1 if bad else 0)
