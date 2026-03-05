import json
from datetime import date
from pathlib import Path

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from agile.models import AppSetting, DepartmentPolicy, Holiday, SystemEmailTemplate, User


class Command(BaseCommand):
    help = 'Importa dati applicativi da export JSON versionato (release bootstrap).'
    SCHEMA_VERSION = 1

    def add_arguments(self, parser):
        parser.add_argument('input_path', help='Percorso del file JSON da importare')
        parser.add_argument(
            '--mode',
            choices=['merge', 'replace'],
            default='merge',
            help='merge=upsert senza cancellazioni, replace=sostituisce policy/festivita/template/app_setting',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula import senza salvare modifiche',
        )

    @staticmethod
    def _as_bool(value, default=False):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {'1', 'true', 'yes', 'si', 'y'}:
            return True
        if text in {'0', 'false', 'no', 'n'}:
            return False
        return default

    @staticmethod
    def _load_payload(path: Path):
        if not path.exists():
            raise CommandError(f'File non trovato: {path}')
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as exc:
            raise CommandError(f'JSON non valido: {exc}') from exc
        if not isinstance(payload, dict):
            raise CommandError('Formato non valido: payload root deve essere un oggetto JSON')
        return payload

    def _validate_schema(self, payload):
        schema_version = payload.get('schema_version')
        if schema_version != self.SCHEMA_VERSION:
            raise CommandError(
                f'schema_version non supportata: {schema_version!r} (attesa: {self.SCHEMA_VERSION})'
            )

    def _sync_groups(self, group_names, counters):
        names = []
        for value in group_names or []:
            name = str(value or '').strip()
            if not name:
                continue
            names.append(name)
        names = sorted(set(names))
        for name in names:
            _, created = Group.objects.get_or_create(name=name)
            counters['groups_created'] += int(created)
            counters['groups_existing'] += int(not created)

    def _sync_users(self, users_payload, counters):
        allowed_departments = {choice[0] for choice in User._meta.get_field('department').choices if choice[0]}
        known_roles = {choice[0] for choice in User._meta.get_field('role').choices}

        imported_users = {}
        for row in users_payload or []:
            username = str((row or {}).get('username') or '').strip()
            if not username:
                counters['users_skipped'] += 1
                self.stderr.write(self.style.WARNING('Utente saltato: username mancante'))
                continue

            user = User.objects.filter(username=username).first()
            created = False
            if not user:
                user = User(username=username)
                user.set_unusable_password()
                created = True

            role = str((row or {}).get('role') or User.Role.EMPLOYEE).strip().upper()
            if role not in known_roles:
                role = User.Role.EMPLOYEE

            department = str((row or {}).get('department') or '').strip()
            if department and department not in allowed_departments:
                self.stderr.write(
                    self.style.WARNING(
                        f'Utente {username}: sede "{department}" non valida, impostata a vuoto'
                    )
                )
                department = ''

            user.email = str((row or {}).get('email') or '').strip()
            user.first_name = str((row or {}).get('first_name') or '').strip()
            user.last_name = str((row or {}).get('last_name') or '').strip()
            user.is_active = self._as_bool((row or {}).get('is_active'), default=True)
            user.role = role
            user.aila_subscribed = self._as_bool((row or {}).get('aila_subscribed'), default=False)
            user.onboarding_pending = self._as_bool((row or {}).get('onboarding_pending'), default=False)
            user.auto_approve = self._as_bool((row or {}).get('auto_approve'), default=False)
            user.department = department
            user.manager = None
            user.save()

            group_names = sorted(
                {
                    str(name or '').strip()
                    for name in ((row or {}).get('groups') or [])
                    if str(name or '').strip()
                }
            )
            groups = [Group.objects.get_or_create(name=name)[0] for name in group_names]
            user.groups.set(groups)

            imported_users[username] = user
            counters['users_created'] += int(created)
            counters['users_updated'] += int(not created)
        return imported_users

    def _assign_managers(self, users_payload, imported_users, counters):
        for row in users_payload or []:
            username = str((row or {}).get('username') or '').strip()
            manager_username = str((row or {}).get('manager_username') or '').strip()
            if not username:
                continue
            user = imported_users.get(username) or User.objects.filter(username=username).first()
            if not user:
                continue
            if not manager_username:
                continue
            if manager_username == username:
                counters['manager_skipped_self'] += 1
                continue
            manager = imported_users.get(manager_username) or User.objects.filter(username=manager_username).first()
            if not manager:
                counters['manager_missing'] += 1
                self.stderr.write(
                    self.style.WARNING(
                        f'Utente {username}: referente "{manager_username}" non trovato, ignorato'
                    )
                )
                continue
            if user.manager_id != manager.id:
                user.manager = manager
                user.save(update_fields=['manager'])
                counters['manager_assigned'] += 1

    def _sync_department_policies(self, rows, mode, counters):
        valid_departments = {choice[0] for choice in DepartmentPolicy._meta.get_field('department').choices}
        keep_departments = set()

        for row in rows or []:
            department = str((row or {}).get('department') or '').strip()
            if not department:
                counters['policies_skipped'] += 1
                continue
            if department not in valid_departments:
                counters['policies_skipped'] += 1
                self.stderr.write(
                    self.style.WARNING(f'Policy saltata: sede "{department}" non valida')
                )
                continue
            keep_departments.add(department)
            obj, created = DepartmentPolicy.objects.get_or_create(department=department)
            obj.max_remote_days = (row or {}).get('max_remote_days')
            obj.february_max_remote_days = (row or {}).get('february_max_remote_days')
            obj.require_on_site_prevalence = self._as_bool(
                (row or {}).get('require_on_site_prevalence'),
                default=True,
            )
            obj.save()
            counters['policies_created'] += int(created)
            counters['policies_updated'] += int(not created)

        if mode == 'replace':
            deleted, _ = DepartmentPolicy.objects.exclude(department__in=keep_departments).delete()
            counters['policies_deleted'] += int(deleted)

    def _sync_holidays(self, rows, mode, counters):
        valid_departments = {choice[0] for choice in Holiday._meta.get_field('department').choices}
        keep_keys = set()

        for row in rows or []:
            day_raw = str((row or {}).get('day') or '').strip()
            try:
                day_value = date.fromisoformat(day_raw)
            except ValueError:
                counters['holidays_skipped'] += 1
                self.stderr.write(self.style.WARNING(f'Festivita saltata: data non valida "{day_raw}"'))
                continue

            department = str((row or {}).get('department') or '').strip()
            if department not in valid_departments:
                counters['holidays_skipped'] += 1
                self.stderr.write(
                    self.style.WARNING(
                        f'Festivita {day_raw}: sede "{department}" non valida, record saltato'
                    )
                )
                continue

            name = str((row or {}).get('name') or '').strip() or 'Festivita'
            keep_keys.add((day_value, department))
            obj, created = Holiday.objects.get_or_create(day=day_value, department=department)
            obj.name = name
            obj.save()
            counters['holidays_created'] += int(created)
            counters['holidays_updated'] += int(not created)

        if mode == 'replace':
            deleted = 0
            for obj in Holiday.objects.all().only('id', 'day', 'department'):
                if (obj.day, obj.department) not in keep_keys:
                    obj.delete()
                    deleted += 1
            counters['holidays_deleted'] += deleted

    def _sync_templates(self, rows, mode, counters):
        valid_keys = {choice[0] for choice in SystemEmailTemplate._meta.get_field('key').choices}
        keep_keys = set()

        for row in rows or []:
            key = str((row or {}).get('key') or '').strip()
            if key not in valid_keys:
                counters['templates_skipped'] += 1
                self.stderr.write(self.style.WARNING(f'Template saltato: key non valida "{key}"'))
                continue

            keep_keys.add(key)
            obj, created = SystemEmailTemplate.objects.get_or_create(
                key=key,
                defaults={
                    'subject_template': str((row or {}).get('subject_template') or '').strip(),
                    'body_template': str((row or {}).get('body_template') or '').strip(),
                },
            )
            if not created:
                obj.subject_template = str((row or {}).get('subject_template') or '').strip()
                obj.body_template = str((row or {}).get('body_template') or '').strip()
                obj.save()
            counters['templates_created'] += int(created)
            counters['templates_updated'] += int(not created)

        if mode == 'replace':
            deleted, _ = SystemEmailTemplate.objects.exclude(key__in=keep_keys).delete()
            counters['templates_deleted'] += int(deleted)

    def _sync_app_setting(self, data, mode, counters):
        current = AppSetting.objects.order_by('id').first()
        if not data:
            if mode == 'replace' and current:
                current.delete()
                counters['app_setting_deleted'] += 1
            return

        if current is None:
            current = AppSetting()
            created = True
        else:
            created = False

        current.date_display_format = str((data or {}).get('date_display_format') or '').strip()
        current.login_logo_url = str((data or {}).get('login_logo_url') or '').strip()
        current.company_name = str((data or {}).get('company_name') or '').strip()
        current.default_from_email = str((data or {}).get('default_from_email') or '').strip()
        current.email_from_name = str((data or {}).get('email_from_name') or '').strip()
        current.copyright_year = (data or {}).get('copyright_year') or None
        current.save()

        counters['app_setting_created'] += int(created)
        counters['app_setting_updated'] += int(not created)

    def handle(self, *args, **options):
        input_path = Path(str(options.get('input_path') or '').strip())
        mode = options.get('mode') or 'merge'
        dry_run = bool(options.get('dry_run'))

        payload = self._load_payload(input_path)
        self._validate_schema(payload)

        counters = {
            'groups_created': 0,
            'groups_existing': 0,
            'users_created': 0,
            'users_updated': 0,
            'users_skipped': 0,
            'manager_assigned': 0,
            'manager_missing': 0,
            'manager_skipped_self': 0,
            'policies_created': 0,
            'policies_updated': 0,
            'policies_deleted': 0,
            'policies_skipped': 0,
            'holidays_created': 0,
            'holidays_updated': 0,
            'holidays_deleted': 0,
            'holidays_skipped': 0,
            'templates_created': 0,
            'templates_updated': 0,
            'templates_deleted': 0,
            'templates_skipped': 0,
            'app_setting_created': 0,
            'app_setting_updated': 0,
            'app_setting_deleted': 0,
        }

        with transaction.atomic():
            self._sync_groups(payload.get('groups') or [], counters)
            imported_users = self._sync_users(payload.get('users') or [], counters)
            self._assign_managers(payload.get('users') or [], imported_users, counters)
            self._sync_department_policies(payload.get('department_policies') or [], mode, counters)
            self._sync_holidays(payload.get('holidays') or [], mode, counters)
            self._sync_templates(payload.get('system_email_templates') or [], mode, counters)
            self._sync_app_setting(payload.get('app_setting'), mode, counters)

            if dry_run:
                transaction.set_rollback(True)

        mode_label = 'DRY-RUN' if dry_run else 'COMPLETED'
        self.stdout.write(self.style.SUCCESS(f'Import {mode_label}: file={input_path}, mode={mode}'))
        self.stdout.write(
            'Gruppi: '
            f'creati={counters["groups_created"]}, '
            f'esistenti={counters["groups_existing"]}'
        )
        self.stdout.write(
            'Utenti: '
            f'creati={counters["users_created"]}, '
            f'aggiornati={counters["users_updated"]}, '
            f'saltati={counters["users_skipped"]}'
        )
        self.stdout.write(
            'Referenti: '
            f'assegnati={counters["manager_assigned"]}, '
            f'mancanti={counters["manager_missing"]}, '
            f'auto-riferimenti saltati={counters["manager_skipped_self"]}'
        )
        self.stdout.write(
            'Policy: '
            f'create={counters["policies_created"]}, '
            f'aggiornate={counters["policies_updated"]}, '
            f'cancellate={counters["policies_deleted"]}, '
            f'saltate={counters["policies_skipped"]}'
        )
        self.stdout.write(
            'Festivita: '
            f'create={counters["holidays_created"]}, '
            f'aggiornate={counters["holidays_updated"]}, '
            f'cancellate={counters["holidays_deleted"]}, '
            f'saltate={counters["holidays_skipped"]}'
        )
        self.stdout.write(
            'Template email: '
            f'creati={counters["templates_created"]}, '
            f'aggiornati={counters["templates_updated"]}, '
            f'cancellati={counters["templates_deleted"]}, '
            f'saltati={counters["templates_skipped"]}'
        )
        self.stdout.write(
            'Impostazioni applicazione: '
            f'creata={counters["app_setting_created"]}, '
            f'aggiornata={counters["app_setting_updated"]}, '
            f'cancellata={counters["app_setting_deleted"]}'
        )
