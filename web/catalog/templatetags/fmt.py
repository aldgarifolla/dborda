"""Формат чисел на страницах: 10049 -> «10 049», 83.4 -> «83,4» (неразрывный пробел, локаль ru).
Подключён как встроенный фильтр (settings.TEMPLATES … builtins), {% load %} не нужен."""
from decimal import Decimal

from django import template
from django.utils.formats import number_format

register = template.Library()


@register.filter
def num(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return value                     # строки («120 шт.»), None и пустые значения — как есть
    return number_format(value, force_grouping=True)
