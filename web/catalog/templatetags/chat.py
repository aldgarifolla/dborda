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
