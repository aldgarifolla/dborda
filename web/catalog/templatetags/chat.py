"""Оформление ответа помощника: абзацы, **жирный** и списки «- …». Весь текст сначала экранируется."""
import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()
BOLD = re.compile(r'\*\*(.+?)\*\*')


def _inline(line):
    return BOLD.sub(r'<strong>\1</strong>', escape(line))


@register.filter
def chat_text(text):
    blocks, items = [], []

    def flush():
        if items:
            blocks.append('<ul>' + ''.join(f'<li>{i}</li>' for i in items) + '</ul>')
            items.clear()

    for line in str(text or '').split('\n'):
        stripped = line.strip()
        if re.match(r'^[-•*]\s+', stripped):
            items.append(_inline(re.sub(r'^[-•*]\s+', '', stripped)))
        elif stripped:
            flush()
            blocks.append(f'<p>{_inline(stripped)}</p>')
        else:
            flush()
    flush()
    return mark_safe(''.join(blocks))


@register.filter
def years(value):
    """31 -> «31 год», 22 -> «22 года», 25 -> «25 лет»."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return value
    if n % 10 == 1 and n % 100 != 11:
        word = 'год'
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        word = 'года'
    else:
        word = 'лет'
    return f'{n} {word}'
