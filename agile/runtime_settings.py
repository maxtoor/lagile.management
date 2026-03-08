from functools import lru_cache

from django.conf import settings
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django.templatetags.static import static


def clear_runtime_settings_cache() -> None:
    _load_db_settings.cache_clear()


def _table_exists(table_name: str) -> bool:
    try:
        return table_name in connection.introspection.table_names()
    except (OperationalError, ProgrammingError):
        return False


@lru_cache(maxsize=1)
def _load_db_settings() -> dict:
    from .models import AppSetting

    table_name = AppSetting._meta.db_table
    if not _table_exists(table_name):
        return {}
    row = AppSetting.objects.order_by('id').first()
    if not row:
        return {}
    return {
        'AGILE_DATE_DISPLAY_FORMAT': (row.date_display_format or '').strip(),
        'AGILE_LOGIN_LOGO_URL': (row.login_logo_url or '').strip(),
        'AGILE_COMPANY_NAME': (row.company_name or '').strip(),
        'AGILE_COPYRIGHT_YEAR': row.copyright_year,
        'DEFAULT_FROM_EMAIL': (row.default_from_email or '').strip(),
        'AGILE_EMAIL_FROM_NAME': (row.email_from_name or '').strip(),
    }


def get_runtime_setting(name: str, fallback=None):
    value = _load_db_settings().get(name)
    if value not in (None, ''):
        return value
    return getattr(settings, name, fallback)


def get_public_base_url() -> str:
    return (get_runtime_setting('AGILE_PUBLIC_BASE_URL', '') or '').strip().rstrip('/')


def build_email_link_context() -> dict:
    base_url = get_public_base_url()
    if not base_url:
        return {
            'public_base_url': '',
            'portal_url': '',
            'admin_url': '',
        }
    return {
        'public_base_url': base_url,
        'portal_url': f'{base_url}/',
        'admin_url': f'{base_url}/admin/',
    }


def build_runtime_ui_context() -> dict:
    login_logo_url = (get_runtime_setting('AGILE_LOGIN_LOGO_URL', '') or '').strip()
    if not login_logo_url:
        login_logo_url = static('agile/informatici_cnr.png')
    return {
        'login_logo_url': login_logo_url,
        'company_name': get_runtime_setting('AGILE_COMPANY_NAME', 'LAgile.Management'),
        'copyright_year': get_runtime_setting('AGILE_COPYRIGHT_YEAR', 2026),
    }
