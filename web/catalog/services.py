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
        raise GrantDenied('Подразделение недоступно')
    with transaction.atomic():
        if action == 'grant':
            UnitGrant.objects.update_or_create(user=target, root_code=root_code, defaults={'is_active': True})
        else:
            updated = UnitGrant.objects.filter(user=target, root_code=root_code, is_active=True).update(is_active=False)
            if not updated:
                raise GrantDenied('Активное разрешение не найдено')
        GrantAudit.objects.create(actor=actor, target=target, root_code=root_code, action=action)
