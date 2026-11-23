from django.db import transaction
from .models import GrantAudit, UnitGrant, UserRole
from . import repository as repo


class GrantDenied(Exception):
    pass


def assign_grant(actor, target, root_code, action):
    """Demo-only restricted delegation: managers can alter viewers' grants inside their own scope."""
    if not actor.is_authenticated or actor.pk == target.pk or not actor.is_active:
        raise GrantDenied('Операция запрещена')
    if actor.is_superuser or target.is_superuser or not target.is_active:
        raise GrantDenied('Операция запрещена')
    if not UserRole.objects.filter(user=actor, role='manager').exists():
        raise GrantDenied('Требуется роль manager')
    if not UserRole.objects.filter(user=target, role='viewer').exists():
        raise GrantDenied('Назначать права можно только пользователям viewer')
    if action not in ('grant', 'revoke') or root_code not in repo.allowed_codes(actor):
        raise GrantDenied('Округ недоступен')
    with transaction.atomic():
        if action == 'grant':
            UnitGrant.objects.update_or_create(user=target, root_code=root_code, defaults={'is_active': True})
        else:
            updated = UnitGrant.objects.filter(user=target, root_code=root_code, is_active=True).update(is_active=False)
            if not updated:
                raise GrantDenied('Активное разрешение не найдено')
        GrantAudit.objects.create(actor=actor, target=target, root_code=root_code, action=action)


# ---------------------------------------------------------------- пользователи (создаёт менеджер)
import re as _re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

USERNAME_RE = _re.compile(r'^[A-Za-z0-9_.-]{3,30}$')
NAME_RE = _re.compile(r"^[A-Za-zА-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі'-]+$")


def _require_manager(actor):
    if not actor.is_authenticated or not actor.is_active or actor.is_superuser:
        raise GrantDenied('Операция запрещена')
    if not UserRole.objects.filter(user=actor, role='manager').exists():
        raise GrantDenied('Требуется роль «менеджер»')


def create_user(actor, full_name, username, role, password, districts):
    """Менеджер создаёт пользователя и сразу выдаёт ему округа — только из своей области доступа.
    Ошибки ввода — ValidationError со словарём {поле: [сообщения]}."""
    _require_manager(actor)
    errors = {}
    full_name = ' '.join(str(full_name or '').split())
    parts = full_name.split(' ') if full_name else []
    if not 2 <= len(parts) <= 3 or not all(NAME_RE.match(p) for p in parts):
        errors['full_name'] = ['Укажите фамилию, имя и (если есть) отчество буквами: «Калижанов Арман Бакытович».']
    username = str(username or '').strip()
    User = get_user_model()
    if not USERNAME_RE.match(username):
        errors['username'] = ['Логин: 3–30 латинских букв, цифр или знаков . _ -']
    elif User.objects.filter(username__iexact=username).exists():
        errors['username'] = ['Такой логин уже есть.']
    if role not in ('viewer', 'manager'):
        errors['role'] = ['Выберите роль.']
    scope = repo.allowed_codes(actor)
    districts = sorted(set(districts or []))
    if not districts:
        errors['districts'] = ['Выберите хотя бы один округ.']
    elif not set(districts) <= scope:
        errors['districts'] = ['Можно выдать только округа из вашей области доступа.']
    candidate = User(username=username, first_name=(parts[1] if len(parts) > 1 else ''), last_name=(parts[0] if parts else ''))
    try:
        validate_password(password or '', user=candidate)
    except ValidationError as exc:
        errors['password'] = list(exc.messages)
    if errors:
        raise ValidationError(errors)
    with transaction.atomic():
        candidate.set_password(password)
        candidate.save()
        UserRole.objects.create(user=candidate, role=role, full_name=full_name)
        GrantAudit.objects.create(actor=actor, target=candidate, root_code='', action='create')
        for code in districts:
            UnitGrant.objects.create(user=candidate, root_code=code, is_active=True)
            GrantAudit.objects.create(actor=actor, target=candidate, root_code=code, action='grant')
    return candidate


def can_manage(actor, target):
    """Менеджер управляет пользователем, если это не он сам, не суперпользователь
    и все активные округа пользователя — в области доступа менеджера."""
    if target.pk == actor.pk or target.is_superuser:
        return False
    codes = set(UnitGrant.objects.filter(user=target, is_active=True).values_list('root_code', flat=True))
    return codes <= repo.allowed_codes(actor)


def set_user_active(actor, target, active):
    _require_manager(actor)
    if not can_manage(actor, target):
        raise GrantDenied('Этим пользователем управлять нельзя')
    if target.is_active == bool(active):
        return
    with transaction.atomic():
        target.is_active = bool(active)
        target.save(update_fields=['is_active'])
        GrantAudit.objects.create(actor=actor, target=target, root_code='', action='enable' if active else 'disable')
