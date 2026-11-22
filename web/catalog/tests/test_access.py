from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from catalog.models import UserRole, UnitGrant, GrantAudit
from catalog.services import assign_grant, GrantDenied


class PermissionSmokeTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.viewer = users.objects.create_user(username='example_viewer', password='StrongDemo123!')
        self.manager = users.objects.create_user(username='example_manager', password='StrongDemo123!')
        self.other = users.objects.create_user(username='example_other', password='StrongDemo123!')
        UserRole.objects.create(user=self.viewer, role='viewer')
        UserRole.objects.create(user=self.manager, role='manager')
        UserRole.objects.create(user=self.other, role='viewer')
        UnitGrant.objects.create(user=self.viewer, root_code='T.1.')
        UnitGrant.objects.create(user=self.manager, root_code='T.')
        self.client.force_login(self.viewer)

    def test_unauthenticated_redirects(self):
        self.client.logout()
        response = self.client.get(reverse('district_list'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    @patch('catalog.views.repo.allowed_codes', return_value={'T.1.'})
    def test_forbidden_district_returns_404(self, mocked_scope):
        response = self.client.get(reverse('district_detail', kwargs={'code': 'T.2.'}))
        self.assertEqual(response.status_code, 404)

    def test_viewer_cannot_manage_grants(self):
        response = self.client.get(reverse('manage_grants'))
        self.assertEqual(response.status_code, 403)

    @patch('catalog.services.repo.allowed_codes', return_value={'T.', 'T.1.'})
    def test_manager_can_grant_inside_scope(self, mocked_scope):
        assign_grant(self.manager, self.other, 'T.1.', 'grant')
        self.assertTrue(UnitGrant.objects.filter(user=self.other, root_code='T.1.', is_active=True).exists())
        self.assertTrue(GrantAudit.objects.filter(actor=self.manager, target=self.other, action='grant').exists())

    @patch('catalog.services.repo.allowed_codes', return_value={'T.', 'T.1.'})
    def test_manager_cannot_grant_outside_scope(self, mocked_scope):
        with self.assertRaises(GrantDenied):
            assign_grant(self.manager, self.other, 'T.2.', 'grant')
        self.assertFalse(UnitGrant.objects.filter(user=self.other, root_code='T.2.').exists())

    @patch('catalog.services.repo.allowed_codes', return_value={'T.', 'T.1.'})
    def test_manager_cannot_modify_own_grants(self, mocked_scope):
        with self.assertRaises(GrantDenied):
            assign_grant(self.manager, self.manager, 'T.1.', 'grant')

    @patch('catalog.services.repo.allowed_codes', return_value={'T.', 'T.1.'})
    def test_manager_cannot_manage_other_manager(self, mocked_scope):
        with self.assertRaises(GrantDenied):
            assign_grant(self.manager, self.manager, 'T.1.', 'grant')
        third_manager = get_user_model().objects.create_user('third_manager', password='StrongDemo123!')
        UserRole.objects.create(user=third_manager, role='manager')
        with self.assertRaises(GrantDenied):
            assign_grant(self.manager, third_manager, 'T.1.', 'grant')

    def test_viewer_cannot_grant(self):
        with self.assertRaises(GrantDenied):
            assign_grant(self.viewer, self.other, 'T.1.', 'grant')

    def test_logout_get_is_not_allowed(self):
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 405)
