from __future__ import annotations

import os
from email.utils import formataddr
from typing import Optional

from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from agile.models import AuditLog, User
from agile.runtime_settings import build_email_link_context, get_runtime_setting


class Command(BaseCommand):
    help = (
        'Verifica se gli utenti locali gestiti via LDAP esistono ancora nella directory. '
        'Se non esistono piu, li disattiva e invia un report ai superuser.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--base-dn',
            dest='base_dn',
            default=os.getenv('LDAP_USER_BASE_DN', ''),
            help='Base DN per la ricerca LDAP (default: LDAP_USER_BASE_DN)',
        )
        parser.add_argument(
            '--user-filter',
            dest='user_filter',
            default=os.getenv('LDAP_USER_FILTER', '(uid=%(user)s)'),
            help='Filtro LDAP utente per verifica puntuale esistenza (default: LDAP_USER_FILTER)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra il risultato senza salvare modifiche nel DB e senza inviare email',
        )

    @staticmethod
    def _sender_from_env() -> Optional[str]:
        from_email = (get_runtime_setting('DEFAULT_FROM_EMAIL', '') or '').strip()
        from_name = (get_runtime_setting('AGILE_EMAIL_FROM_NAME', '') or '').strip()
        if not from_email:
            return None
        if not from_name:
            return from_email
        return formataddr((from_name, from_email))

    @staticmethod
    def _notify_superusers(*, missing_users: list[dict], dry_run: bool) -> None:
        if dry_run or not missing_users:
            return

        recipients = list(
            User.objects.filter(is_superuser=True, is_active=True)
            .exclude(email__isnull=True)
            .exclude(email__exact='')
            .values_list('email', flat=True)
        )
        if not recipients:
            return

        links = build_email_link_context()
        admin_url = (links.get('admin_url') or '').strip()
        body_lines = [
            'Il controllo periodico di presenza LDAP ha disattivato utenti locali non piu presenti nella directory.',
            '',
            f'Utenti disattivati: {len(missing_users)}',
            '',
        ]
        for item in missing_users:
            body_lines.append(f"- {item['username']} ({item['full_name']}) - {item['email']}")
        if admin_url:
            body_lines.extend(['', f'Pannello amministrativo: {admin_url}'])

        send_mail(
            subject=f'Utenti disattivati per assenza da LDAP: {len(missing_users)}',
            message='\n'.join(body_lines),
            from_email=Command._sender_from_env(),
            recipient_list=recipients,
            fail_silently=False,
        )

    @staticmethod
    def _user_display_name(user: User) -> str:
        full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
        return full_name or user.username

    def handle(self, *args, **options):
        try:
            import ldap
            from ldap.filter import escape_filter_chars
        except ImportError:
            self.stderr.write(self.style.ERROR('Libreria python-ldap non disponibile'))
            return

        if os.getenv('LDAP_ENABLED', '0') != '1':
            self.stdout.write(self.style.WARNING('LDAP non attivo (LDAP_ENABLED != 1), nessuna azione eseguita'))
            return

        server_uri = os.getenv('LDAP_SERVER_URI', '').strip()
        bind_dn = os.getenv('LDAP_BIND_DN', '').strip()
        bind_password = os.getenv('LDAP_BIND_PASSWORD', '')
        base_dn = (options.get('base_dn') or '').strip()
        user_filter = (options.get('user_filter') or '').strip()
        dry_run = bool(options.get('dry_run'))

        if not server_uri:
            self.stderr.write(self.style.ERROR('LDAP_SERVER_URI non configurato'))
            return
        if not base_dn:
            self.stderr.write(self.style.ERROR('LDAP_USER_BASE_DN (o --base-dn) non configurato'))
            return
        if '%(user)s' not in user_filter:
            self.stderr.write(self.style.ERROR("LDAP_USER_FILTER deve contenere il placeholder '%(user)s'"))
            return

        attr_username = os.getenv('LDAP_ATTR_USERNAME', 'uid')
        conn = ldap.initialize(server_uri)
        conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)

        try:
            if bind_dn:
                conn.simple_bind_s(bind_dn, bind_password)
            else:
                conn.simple_bind_s()
        except ldap.LDAPError as exc:
            self.stderr.write(self.style.ERROR(f'Errore bind LDAP: {exc}'))
            return

        candidates = list(
            User.objects.exclude(is_superuser=True)
            .filter(is_active=True, password__startswith='!')
            .only('id', 'username', 'first_name', 'last_name', 'email', 'is_active')
        )

        checked = 0
        missing_count = 0
        deactivated = 0
        missing_users: list[dict] = []

        try:
            with transaction.atomic():
                for user in candidates:
                    checked += 1
                    ldap_filter = user_filter % {'user': escape_filter_chars(user.username)}
                    try:
                        results = conn.search_s(base_dn, ldap.SCOPE_SUBTREE, ldap_filter, [attr_username])
                    except ldap.LDAPError as exc:
                        self.stderr.write(
                            self.style.ERROR(f"Errore LDAP durante la verifica di {user.username}: {exc}")
                        )
                        raise

                    found = any(dn and entry for dn, entry in results)
                    if found:
                        continue

                    missing_count += 1
                    missing_users.append(
                        {
                            'username': user.username,
                            'full_name': self._user_display_name(user),
                            'email': (user.email or '-').strip() or '-',
                        }
                    )

                    if dry_run:
                        continue

                    user.is_active = False
                    user.save(update_fields=['is_active'])
                    deactivated += 1
                    AuditLog.track(
                        actor=None,
                        action='ldap_user_deactivated_missing_from_directory',
                        target_type='User',
                        target_id=user.id,
                        metadata={
                            'username': user.username,
                            'email': user.email or '',
                            'checked_at': timezone.now().isoformat(),
                        },
                    )

                if dry_run:
                    transaction.set_rollback(True)
        except Exception:
            return
        finally:
            try:
                conn.unbind_s()
            except Exception:
                pass

        try:
            self._notify_superusers(missing_users=missing_users, dry_run=dry_run)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f'Invio email superuser fallito: {exc}'))

        suffix = ' (dry-run, nessuna modifica salvata)' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                f'Controllo presenza LDAP completato: verificati={checked}, assenti={missing_count}, '
                f'disattivati={deactivated}{suffix}'
            )
        )
