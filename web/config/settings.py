"""Local, synthetic-data MVP; not production deployment settings."""
import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']
DEBUG = os.environ.get('DJANGO_DEBUG') == '1'
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
INSTALLED_APPS = [
    'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages',
    'django.contrib.staticfiles', 'catalog',
]
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.debug',
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]
WSGI_APPLICATION = 'config.wsgi.application'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.environ.get('DB_HOST', 'db'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'NAME': 'registry_auth',
        'USER': 'registry_web_auth',
        'PASSWORD': os.environ['WEB_AUTH_PASSWORD'],
        'OPTIONS': {'options': '-c statement_timeout=5000'},
    },
    'military': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': os.environ.get('DB_HOST', 'db'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'NAME': 'military_lab',
        'USER': 'registry_reader',
        'PASSWORD': os.environ['APP_READER_PASSWORD'],
        'OPTIONS': {'options': '-c statement_timeout=5000 -c default_transaction_read_only=on'},
    },
}
# Pure Django tests use SQLite for auth/grants while domain repo is mocked.
if os.environ.get('DJANGO_TEST_SQLITE') == '1':
    DATABASES['default'] = {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}
DATABASE_ROUTERS = ['catalog.router.SeparateDatabasesRouter']

# Помощник: пусто — разбор по ключевым словам; 'catalog.assistant.ollama.OllamaPlanner' — локальная модель.
ASSISTANT_PROVIDER = os.environ.get('ASSISTANT_PROVIDER', '')
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://host.docker.internal:11434')
OLLAMA_MODEL = os.environ.get('OLLAMA_MODEL', 'qwen2.5:14b')
OLLAMA_TIMEOUT = int(os.environ.get('OLLAMA_TIMEOUT', '120'))
# Облачная модель через OpenAI-совместимый API (catalog.assistant.openai_compat): провайдер и модель.
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', '')
LLM_MODEL = os.environ.get('LLM_MODEL', '')
CLAUDE_MODEL = os.environ.get('CLAUDE_MODEL', 'claude-haiku-5-5')
if os.environ.get('DJANGO_TEST_SQLITE') == '1':
    ASSISTANT_PROVIDER = ''   # тесты не обращаются к модели
LANGUAGE_CODE = 'ru'
TIME_ZONE = 'Asia/Almaty'
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_SAMESITE = 'Strict'
SECURE_REFERRER_POLICY = 'same-origin'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
]
