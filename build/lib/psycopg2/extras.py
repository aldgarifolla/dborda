"""execute_values() с тем же поведением, что в psycopg2.extras."""


def execute_values(cur, sql, argslist, template=None, page_size=100):
    pre, sep, post = sql.partition('%s')
    if not sep or '%s' in post:
        raise ValueError('execute_values: в запросе должен быть ровно один %s')
    pre, post = pre.replace('%%', '%'), post.replace('%%', '%')
    rows = list(argslist)
    for i in range(0, len(rows), page_size):
        page = rows[i:i + page_size]
        tpl = template or '(' + ','.join(['%s'] * len(page[0])) + ')'
        cur.execute(pre + ','.join(cur.mogrify(tpl, r) for r in page) + post)
