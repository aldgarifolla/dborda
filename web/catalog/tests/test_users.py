"""Пользователи: отображаемое имя, создание менеджером, отключение, ограничения по округам."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from catalog.models import GrantAudit, UnitGrant, UserRole
from catalog.services import GrantDenied, create_user, set_user_active

SCOPE = {'ОКР-АСТ', 'ОКР-ВОС'}
GOOD_PASSWORD = 'Pole-Smena-2026!'


@patch('catalog.repository.allowed_codes', lambda user: SCOPE if user.username == 'boss' else set())
class UserServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.boss = User.objects.create_user('boss', password=GOOD_PASSWORD)
        UserRole.objects.create(user=self.boss, role='manager', full_name='Калижанов Арман Бакытович')
        self.viewer = User.objects.create_user('viewer1', password=GOOD_PASSWORD)
        UserRole.objects.create(user=self.viewer, role='viewer')

    def test_short_and_given_names(self):
        role = self.boss.demo_role
        self.assertEqual(role.short_name, 'Калижанов А.Б.')
        self.assertEqual(role.given_names, 'Арман Бакытович')
        self.assertEqual(role.initials, 'КА')
        self.assertEqual(self.viewer.demo_role.short_name, 'viewer1')

    def test_create_user_with_grants_and_audit(self):
        user = create_user(self.boss, 'Сериков Ержан Маратович', 'serikov', 'viewer', GOOD_PASSWORD, ['ОКР-АСТ'])
        self.assertTrue(user.check_password(GOOD_PASSWORD))
        self.assertEqual(user.demo_role.full_name, 'Сериков Ержан Маратович')
        self.assertEqual(list(UnitGrant.objects.filter(user=user).values_list('root_code', flat=True)), ['ОКР-АСТ'])
        self.assertEqual(set(GrantAudit.objects.filter(target=user).values_list('action', flat=True)), {'create', 'grant'})

    def test_validation_errors(self):
        with self.assertRaises(ValidationError) as ctx:
            create_user(self.boss, 'Иванов', 'bad login!', 'admin', '123', ['ОКР-ЮГ'])
        self.assertEqual(set(ctx.exception.message_dict), {'full_name', 'username', 'role', 'password', 'districts'})
        with self.assertRaises(ValidationError) as ctx:
            create_user(self.boss, 'Сериков Ержан', 'VIEWER1', 'viewer', GOOD_PASSWORD, ['ОКР-АСТ'])
        self.assertIn('username', ctx.exception.message_dict)
        self.assertFalse(get_user_model().objects.filter(username='serikov').exists())

    def test_viewer_cannot_create(self):
        with self.assertRaises(GrantDenied):
            create_user(self.viewer, 'Сериков Ержан', 'serikov', 'viewer', GOOD_PASSWORD, ['ОКР-АСТ'])

    def test_disable_only_inside_scope_and_not_self(self):
        UnitGrant.objects.create(user=self.viewer, root_code='ОКР-АСТ')
        set_user_active(self.boss, self.viewer, False)
        self.viewer.refresh_from_db()
        self.assertFalse(self.viewer.is_active)
        with self.assertRaises(GrantDenied):
            set_user_active(self.boss, self.boss, False)
        other = get_user_model().objects.create_user('south', password=GOOD_PASSWORD)
        UserRole.objects.create(user=other, role='viewer')
        UnitGrant.objects.create(user=other, root_code='ОКР-ЮГ')
        with self.assertRaises(GrantDenied):
            set_user_active(self.boss, other, False)


@patch('catalog.repository.allowed_codes', lambda user: SCOPE if user.username == 'boss' else set())
@patch('catalog.repository.list_districts', lambda scope: [{'district_code': c, 'short_name': c} for c in sorted(scope)])
class UserPageTests(TestCase):
    def setUp(self):
        self.boss = get_user_model().objects.create_user('boss', password=GOOD_PASSWORD)
        UserRole.objects.create(user=self.boss, role='manager', full_name='Калижанов Арман Бакытович')
        self.client.force_login(self.boss)

    def test_page_shows_name_and_creates_user(self):
        page = self.client.get(reverse('manage_grants')).content.decode()
        self.assertIn('Калижанов А.Б.', page)
        self.assertIn('Новый пользователь', page)
        response = self.client.post(reverse('user_create'), {'full_name': 'Сериков Ержан Маратович', 'username': 'serikov',
                                                             'role': 'viewer', 'password': GOOD_PASSWORD,
                                                             'districts': ['ОКР-ВОС']})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(username='serikov').exists())
        self.assertIn('Сериков Ержан Маратович', self.client.get(reverse('manage_grants')).content.decode())

    def test_form_errors_are_shown(self):
        self.client.post(reverse('user_create'), {'full_name': 'Х', 'username': 'x', 'role': 'viewer', 'password': '1'})
        page = self.client.get(reverse('manage_grants')).content.decode()
        self.assertIn('field-error', page)
        self.assertIn('Пользователь не создан', page)

    def test_viewer_gets_403(self):
        viewer = get_user_model().objects.create_user('viewer2', password=GOOD_PASSWORD)
        UserRole.objects.create(user=viewer, role='viewer')
        self.client.force_login(viewer)
        self.assertEqual(self.client.post(reverse('user_create'), {}).status_code, 403)
