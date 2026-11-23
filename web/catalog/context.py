"""Кто вошёл: отображаемое имя для боковой панели и приветствия (ФИО вместо логина)."""


def person(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}
    role = getattr(user, 'demo_role', None)
    if role is None:
        name = user.get_full_name() or user.username
        return {'me': {'short': name, 'given': name, 'initials': name[:1].upper(), 'role': ''}}
    return {'me': {'short': role.short_name, 'given': role.given_names, 'initials': role.initials,
                   'role': 'менеджер' if role.role == 'manager' else 'наблюдатель'}}
