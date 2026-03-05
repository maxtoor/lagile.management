import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.utils import timezone

from agile.models import AppSetting, DepartmentPolicy, Holiday, SystemEmailTemplate, User


class Command(BaseCommand):
    help = 'Esporta dati applicativi per migrazione/rilascio (JSON versionato).'
    SCHEMA_VERSION = 1

    def add_arguments(self, parser):
        parser.add_argument(
            'output_path',
            nargs='?',
            help='Percorso file output JSON (default: release-export-YYYYMMDD-HHMMSS.json)',
        )
        parser.add_argument(
            '--indent',
            type=int,
            default=2,
            help='Indentazione JSON (default: 2)',
        )

    @staticmethod
    def _default_output_path() -> str:
        stamp = timezone.localtime().strftime('%Y%m%d-%H%M%S')
        return f'release-export-{stamp}.json'

    def handle(self, *args, **options):
        output_path = (options.get('output_path') or '').strip() or self._default_output_path()
        indent = int(options.get('indent') or 2)

        users = []
        for user in User.objects.select_related('manager').prefetch_related('groups').order_by('username'):
            users.append(
                {
                    'username': user.username,
                    'email': user.email or '',
                    'first_name': user.first_name or '',
                    'last_name': user.last_name or '',
                    'is_active': bool(user.is_active),
                    'role': user.role,
                    'aila_subscribed': bool(user.aila_subscribed),
                    'onboarding_pending': bool(user.onboarding_pending),
                    'auto_approve': bool(user.auto_approve),
                    'department': user.department or '',
                    'manager_username': user.manager.username if user.manager else '',
                    'groups': sorted(user.groups.values_list('name', flat=True)),
                }
            )

        group_names = sorted(Group.objects.order_by('name').values_list('name', flat=True))

        department_policies = [
            {
                'department': row.department,
                'max_remote_days': row.max_remote_days,
                'february_max_remote_days': row.february_max_remote_days,
                'require_on_site_prevalence': bool(row.require_on_site_prevalence),
            }
            for row in DepartmentPolicy.objects.order_by('department')
        ]

        holidays = [
            {
                'day': row.day.isoformat(),
                'name': row.name,
                'department': row.department or '',
            }
            for row in Holiday.objects.order_by('day', 'department')
        ]

        templates = [
            {
                'key': row.key,
                'subject_template': row.subject_template,
                'body_template': row.body_template,
            }
            for row in SystemEmailTemplate.objects.order_by('key')
        ]

        app_setting = AppSetting.objects.order_by('id').first()
        app_setting_payload = None
        if app_setting:
            app_setting_payload = {
                'date_display_format': app_setting.date_display_format or '',
                'login_logo_url': app_setting.login_logo_url or '',
                'company_name': app_setting.company_name or '',
                'copyright_year': app_setting.copyright_year,
                'default_from_email': app_setting.default_from_email or '',
                'email_from_name': app_setting.email_from_name or '',
            }

        payload = {
            'schema_version': self.SCHEMA_VERSION,
            'exported_at': timezone.localtime().isoformat(),
            'application': {
                'name': 'LAgile.management',
                'version': getattr(settings, 'AGILE_APP_VERSION', '2.0.0'),
            },
            'users': users,
            'groups': group_names,
            'department_policies': department_policies,
            'holidays': holidays,
            'system_email_templates': templates,
            'app_setting': app_setting_payload,
        }

        target = Path(output_path)
        if target.parent and str(target.parent) != '.':
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=indent), encoding='utf-8')

        self.stdout.write(
            self.style.SUCCESS(
                'Export completato: '
                f'file={target}, utenti={len(users)}, gruppi={len(group_names)}, '
                f'policy={len(department_policies)}, festivita={len(holidays)}, template={len(templates)}'
            )
        )
