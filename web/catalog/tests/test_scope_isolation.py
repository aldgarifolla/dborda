"""Регресс-тесты на ограничение области доступа (scope): наблюдатель видит только выданные округа.

Главный риск приложения — чтобы пользователь не добрался до чужого округа ни по прямой ссылке,
ни через помощника. repository подменяется моками, PostgreSQL не нужен (как в остальных тестах).
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from catalog.assistant import tools
from catalog.models import UnitGrant, UserRole
from catalog.services import GrantDenied, create_user

SCOPE = {'ОКР-АСТ'}          # наблюдателю выдан только округ «Астана»


class ForeignObjectReturns404Tests(TestCase):
    """Прямой переход по ссылке на чужой округ/бригаду/подразделение/человека → 404."""

    def setUp(self):
        users = get_user_model()
        self.viewer = users.objects.create_user(username='iso_viewer', password='StrongDemo123!')
        UserRole.objects.create(user=self.viewer, role='viewer')
        UnitGrant.objects.create(user=self.viewer, root_code='ОКР-АСТ')
        self.client.force_login(self.viewer)

    @patch('catalog.views.repo.allowed_codes', return_value=set(SCOPE))
    def test_foreign_district_detail_404(self, _scope):
        r = self.client.get(reverse('district_detail', kwargs={'code': 'ОКР-ВОС'}))
        self.assertEqual(r.status_code, 404)

    @patch('catalog.views.repo.allowed_codes', return_value=set(SCOPE))
    def test_foreign_district_formation_404(self, _scope):
        r = self.client.get(reverse('formation_detail', kwargs={'code': 'ОКР-ВОС', 'fcode': 'ВОС-1'}))
        self.assertEqual(r.status_code, 404)

    @patch('catalog.views.repo.allowed_codes', return_value=set(SCOPE))
    def test_foreign_district_subunit_404(self, _scope):
        r = self.client.get(reverse('subunit_detail',
                                     kwargs={'code': 'ОКР-ВОС', 'fcode': 'ВОС-1', 'scode': 'ВОС-1.Б1'}))
        self.assertEqual(r.status_code, 404)

    @patch('catalog.views.repo.get_formation', return_value=None)
    @patch('catalog.views.repo.get_district', return_value={'district_code': 'ОКР-АСТ'})
    @patch('catalog.views.repo.allowed_codes', return_value=set(SCOPE))
    def test_formation_in_other_district_404_and_scoped(self, _scope, _district, m_formation):
        """Свой округ в адресе, но бригада чужого округа: scoped-запрос вернёт None → 404.
        Заодно проверяем, что во view передаётся именно область пользователя."""
        r = self.client.get(reverse('formation_detail', kwargs={'code': 'ОКР-АСТ', 'fcode': 'ВОС-1'}))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(m_formation.call_args.args[1], SCOPE)   # get_formation(fcode, scope)

    @patch('catalog.views.repo.get_person', return_value=None)
    @patch('catalog.views.repo.allowed_codes', return_value=set(SCOPE))
    def test_foreign_person_card_404_and_scoped(self, _scope, m_person):
        r = self.client.get(reverse('person_detail', kwargs={'number': 'ЛН-000001'}))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(m_person.call_args.args[1], SCOPE)      # get_person(number, scope)


class ManagerOnlyViewsTests(TestCase):
    """Наблюдатель не достаёт до управления пользователями даже прямым POST."""

    def setUp(self):
        users = get_user_model()
        self.viewer = users.objects.create_user(username='iso_viewer2', password='StrongDemo123!')
        UserRole.objects.create(user=self.viewer, role='viewer')
        self.client.force_login(self.viewer)

    def test_viewer_cannot_open_user_create(self):
        r = self.client.post(reverse('user_create'),
                             {'full_name': 'Тестов Тест Тестович', 'username': 'nope',
                              'role': 'viewer', 'password': 'StrongDemo123!', 'districts': ['ОКР-АСТ']})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(get_user_model().objects.filter(username='nope').exists())

    def test_viewer_cannot_toggle_user(self):
        r = self.client.post(reverse('user_toggle', kwargs={'pk': self.viewer.pk}), {'active': '0'})
        self.assertEqual(r.status_code, 403)


class AssistantScopeInjectionTests(TestCase):
    """Помощник не может расширить область: scope задаётся сервером, модель на него не влияет."""

    def test_run_rejects_model_supplied_scope_argument(self):
        # «scope» нет среди параметров инструмента — лишний аргумент отклоняется
        with self.assertRaises(tools.ToolError):
            tools.run('district_summary', {'district': 'ОКР-АСТ', 'scope': {'ОКР-ВОС'}}, set(SCOPE))

    def test_district_resolver_rejects_out_of_scope_code(self):
        with self.assertRaises(tools.ToolError):
            tools._district(set(SCOPE), 'ОКР-ВОС')

    def test_summary_tool_refuses_foreign_district(self):
        with self.assertRaises(tools.ToolError):
            tools.run('district_summary', {'district': 'ОКР-ВОС'}, set(SCOPE))

    def test_tool_forwards_server_scope_to_repository(self):
        with patch('catalog.assistant.tools.repo.list_districts', return_value=[]) as m:
            tools.run('list_districts', {}, set(SCOPE))
            m.assert_called_once_with(SCOPE)

    def test_unknown_tool_rejected(self):
        with self.assertRaises(tools.ToolError):
            tools.run('run_raw_sql', {'sql': 'select 1'}, set(SCOPE))


class CreateUserScopeTests(TestCase):
    """Менеджер выдаёт только округа из своей области; наблюдатель создавать людей не может."""

    def setUp(self):
        users = get_user_model()
        self.manager = users.objects.create_user(username='iso_mgr', password='StrongDemo123!')
        UserRole.objects.create(user=self.manager, role='manager')
        self.viewer = users.objects.create_user(username='iso_v3', password='StrongDemo123!')
        UserRole.objects.create(user=self.viewer, role='viewer')

    @patch('catalog.services.repo.allowed_codes', return_value=set(SCOPE))
    def test_viewer_cannot_create_user(self, _scope):
        with self.assertRaises(GrantDenied):
            create_user(self.viewer, 'Тестов Тест Тестович', 'newbie', 'viewer', 'StrongDemo123!', ['ОКР-АСТ'])

    @patch('catalog.services.repo.allowed_codes', return_value=set(SCOPE))
    def test_manager_cannot_grant_district_outside_scope(self, _scope):
        with self.assertRaises(ValidationError) as cm:
            create_user(self.manager, 'Тестов Тест Тестович', 'newbie', 'viewer', 'StrongDemo123!', ['ОКР-ВОС'])
        self.assertIn('districts', cm.exception.message_dict)
        self.assertFalse(get_user_model().objects.filter(username='newbie').exists())

    @patch('catalog.services.repo.allowed_codes', return_value=set(SCOPE))
    def test_manager_creates_user_within_scope(self, _scope):
        user = create_user(self.manager, 'Тестов Тест Тестович', 'newbie', 'viewer', 'StrongDemo123!', ['ОКР-АСТ'])
        self.assertTrue(UnitGrant.objects.filter(user=user, root_code='ОКР-АСТ', is_active=True).exists())
        self.assertFalse(UnitGrant.objects.filter(user=user).exclude(root_code='ОКР-АСТ').exists())
