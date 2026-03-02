import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def csv_env(name: str, default: str) -> list[str]:
    return [v.strip() for v in os.getenv(name, default).split(',') if v.strip()]

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-secret-change-me')
DEBUG = os.getenv('DEBUG', '0') == '1'
ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]
AGILE_SITES = csv_env('AGILE_SITES', 'Napoli,Catania,Sassari,Padova')
AGILE_DATE_DISPLAY_FORMAT = os.getenv('AGILE_DATE_DISPLAY_FORMAT', 'IT').upper()
AGILE_LOGIN_LOGO_URL = os.getenv('AGILE_LOGIN_LOGO_URL', '').strip()

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework.authtoken',
    'agile',
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

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'agile_work'),
        'USER': os.getenv('POSTGRES_USER', 'agile'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', 'agile'),
        'HOST': os.getenv('POSTGRES_HOST', '127.0.0.1'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
    }
}

AUTH_USER_MODEL = 'agile.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'it-it'
TIME_ZONE = os.getenv('TIME_ZONE', 'Europe/Rome')
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.getenv('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '25'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', '0') == '1'
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', '0') == '1'
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@istituto.local')

AUTHENTICATION_BACKENDS = ['django.contrib.auth.backends.ModelBackend']

if os.getenv('LDAP_ENABLED', '0') == '1':
    import ldap
    from django_auth_ldap.config import LDAPSearch

    AUTHENTICATION_BACKENDS = [
        'django_auth_ldap.backend.LDAPBackend',
        'django.contrib.auth.backends.ModelBackend',
    ]

    AUTH_LDAP_SERVER_URI = os.getenv('LDAP_SERVER_URI', 'ldap://localhost:389')
    AUTH_LDAP_BIND_DN = os.getenv('LDAP_BIND_DN', '')
    AUTH_LDAP_BIND_PASSWORD = os.getenv('LDAP_BIND_PASSWORD', '')
    AUTH_LDAP_USER_SEARCH = LDAPSearch(
        os.getenv('LDAP_USER_BASE_DN', 'dc=example,dc=org'),
        ldap.SCOPE_SUBTREE,
        os.getenv('LDAP_USER_FILTER', '(uid=%(user)s)'),
    )
    AUTH_LDAP_USER_ATTR_MAP = {
        'username': os.getenv('LDAP_ATTR_USERNAME', 'uid'),
        'first_name': os.getenv('LDAP_ATTR_FIRST_NAME', 'givenName'),
        'last_name': os.getenv('LDAP_ATTR_LAST_NAME', 'sn'),
        'email': os.getenv('LDAP_ATTR_EMAIL', 'mail'),
    }
