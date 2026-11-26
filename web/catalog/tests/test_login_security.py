"""Тесты усиления входа: лимит неудачных попыток и запрет «новый пароль == старый»."""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.auth import StrictPasswordChangeForm

PW = 'OldPass-12345!'


@override_settings(LOGIN_MAX_ATTEMPTS=3, LOGIN_LOCK_SECONDS=900)
class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        get_user_model().objects.create_user(username='victim', password=PW)

    def _fail(self):
        return self.client.post(reverse('login'), {'username': 'victim', 'password': 'wrong'})

    def test_locks_after_threshold_even_with_correct_password(self):
        for _ in range(3):
            self.assertEqual(self._fail().status_code, 200)        # обычная «неверный пароль»
        # порог исчерпан — даже верный пароль не пускает
        r = self.client.post(reverse('login'), {'username': 'victim', 'password': PW})
        self.assertEqual(r.status_code, 429)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_success_before_threshold_resets_counter(self):
        self._fail()
        self._fail()
        ok = self.client.post(reverse('login'), {'username': 'victim', 'password': PW})
        self.assertEqual(ok.status_code, 302)                      # пустили
        self.assertIn('_auth_user_id', self.client.session)
        self.client.logout()
        # счётчик сброшен: снова можно ошибаться без блокировки
        self.assertEqual(self._fail().status_code, 200)


class StrictPasswordChangeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='changer', password=PW)

    def test_rejects_new_equal_to_old(self):
        form = StrictPasswordChangeForm(self.user, {
            'old_password': PW, 'new_password1': PW, 'new_password2': PW})
        self.assertFalse(form.is_valid())
        self.assertIn('new_password1', form.errors)

    def test_accepts_different_new_password(self):
        form = StrictPasswordChangeForm(self.user, {
            'old_password': PW, 'new_password1': 'Different-67890!', 'new_password2': 'Different-67890!'})
        self.assertTrue(form.is_valid(), form.errors)
