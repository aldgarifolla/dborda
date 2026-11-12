import secrets
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from catalog.models import UserRole, UnitGrant
from catalog.repository import select


class Command(BaseCommand):
    help = 'Создать двух учебных пользователей с разными областями доступа'

    def handle(self, *args, **kwargs):
        roots = select("""SELECT unit_code, short_name FROM registry_api.units
                          WHERE country='РК' ORDER BY length(unit_code), unit_code LIMIT 1""")
        if not roots:
            raise RuntimeError('Нет учебного корня РК')
        manager_code = roots[0]['unit_code']
        children = select('''SELECT unit_code, short_name FROM registry_api.units
                             WHERE parent_code=%s ORDER BY unit_code LIMIT 1''', [manager_code])
        viewer_code = children[0]['unit_code'] if children else manager_code
        users = get_user_model()
        for name, role, root_code in (
            ('demo_manager', 'manager', manager_code),
            ('demo_viewer', 'viewer', viewer_code),
        ):
            user, created = users.objects.get_or_create(username=name)
            if created:
                password = secrets.token_urlsafe(18)
                user.set_password(password)
                user.save(update_fields=['password'])
                self.stdout.write(f'НОВЫЙ пользователь {name} | пароль: {password}')
            else:
                self.stdout.write(f'{name} уже существует; пароль оставлен прежним.')
            UserRole.objects.update_or_create(user=user, defaults={'role': role})
            UnitGrant.objects.update_or_create(user=user, root_code=root_code,
                                                defaults={'is_active': True})
            self.stdout.write(f'  Доступ от подразделения: {root_code}')
        self.stdout.write('Учебные пользователи созданы. Сохраните новые пароли локально.')
