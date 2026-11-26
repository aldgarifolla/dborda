"""Защита входа от перебора пароля и запрет «новый пароль == старый».

Троттлинг на кэше Django (по умолчанию LocMemCache): считаем неудачные попытки по IP
и временно блокируем после порога. Без внешних зависимостей. За обратным прокси нужно,
чтобы REMOTE_ADDR был реальным адресом клиента (или настроить доверенный X-Forwarded-For).
"""
from django.conf import settings
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.exceptions import ValidationError

def _max_attempts():
    return getattr(settings, 'LOGIN_MAX_ATTEMPTS', 10)          # после стольких неудач — блок


def _lock_seconds():
    return getattr(settings, 'LOGIN_LOCK_SECONDS', 900)         # длительность окна/блокировки, сек


def _client_ip(request):
    return request.META.get('REMOTE_ADDR') or 'unknown'


def _key(request):
    return 'login-fail:%s' % _client_ip(request)


def _attempts(request):
    try:
        return cache.get(_key(request), 0)
    except Exception:
        return 0


class ThrottledLoginView(LoginView):
    """LoginView с лимитом неудачных попыток по IP и временной блокировкой."""

    def _locked_response(self):
        context = self.get_context_data(form=self.get_form(), locked=True)
        return self.render_to_response(context, status=429)

    def post(self, request, *args, **kwargs):
        if _attempts(request) >= _max_attempts():
            return self._locked_response()
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('locked', _attempts(self.request) >= _max_attempts())
        return context

    def form_valid(self, form):
        try:
            cache.delete(_key(self.request))      # успех — сбрасываем счётчик
        except Exception:
            pass
        return super().form_valid(form)

    def form_invalid(self, form):
        try:
            cache.set(_key(self.request), _attempts(self.request) + 1, _lock_seconds())
        except Exception:
            pass
        return super().form_invalid(form)


class StrictPasswordChangeForm(PasswordChangeForm):
    """Запрещает ставить новый пароль, совпадающий с текущим."""

    def clean_new_password1(self):
        new = self.cleaned_data.get('new_password1')
        old = self.cleaned_data.get('old_password')
        if old and new and old == new:
            raise ValidationError('Новый пароль должен отличаться от текущего.')
        return new
