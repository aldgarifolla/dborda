import secrets
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from catalog.models import UserRole, UnitGrant
from catalog.repository import select


class Command(BaseCommand):
    help = 'Создать двух учебных пользователей с разными областями доступа (по округам)'

    def handle(self, *args, **kwargs):
        codes = [r['district_code'] for r in select('SELECT district_code FROM registry_api.districts ORDER BY sort_order')]
        if not codes:
            raise RuntimeError('В базе нет учебных округов: сначала примените build/stages/70_districts.sql')
        users = get_user_model()
        for name, role, granted in (('demo_manager', 'manager', codes), ('demo_viewer', 'viewer', codes[:1])):
            user, created = users.objects.get_or_create(username=name)
            if created:
                password = secrets.token_urlsafe(18)
                user.set_password(password)
                user.save(update_fields=['password'])
                self.stdout.write(f'НОВЫЙ пользователь {name} | пароль: {password}')
            else:
                self.stdout.write(f'{name} уже существует; пароль оставлен прежним.')
            UserRole.objects.update_or_create(user=user, defaults={'role': role})
            # права на узлы прежней подробной структуры больше не действуют
            UnitGrant.objects.filter(user=user).exclude(root_code__in=granted).update(is_active=False)
            for code in granted:
                UnitGrant.objects.update_or_create(user=user, root_code=code, defaults={'is_active': True})
            self.stdout.write(f'  Доступ к округам: {", ".join(granted)}')
        self.stdout.write('Учебные пользователи созданы. Сохраните новые пароли локально.')
