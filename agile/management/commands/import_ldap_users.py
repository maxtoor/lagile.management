import os

from django.core.management.base import BaseCommand
from django.db import transaction

from agile.models import SITE_CHOICES, User


class Command(BaseCommand):
    help = 'Importa utenti da LDAP nel DB locale e li imposta non attivi.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--filter',
            dest='ldap_filter',
            default=os.getenv('LDAP_IMPORT_FILTER', '(objectClass=person)'),
            help='Filtro LDAP per selezionare gli utenti da importare',
        )
        parser.add_argument(
            '--base-dn',
            dest='base_dn',
            default=os.getenv('LDAP_USER_BASE_DN', ''),
            help='Base DN per la ricerca LDAP (default: LDAP_USER_BASE_DN)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra il risultato senza salvare modifiche nel DB',
        )

    @staticmethod
    def _decode_first(values):
        if not values:
            return ''
        value = values[0]
        if isinstance(value, bytes):
            return value.decode('utf-8', errors='ignore').strip()
        return str(value).strip()

    @staticmethod
    def _normalize_site(value: str) -> str:
        allowed_sites = {choice[0] for choice in SITE_CHOICES}
        return value if value in allowed_sites else ''

    def handle(self, *args, **options):
        try:
            import ldap
        except ImportError:
            self.stderr.write(self.style.ERROR('Libreria python-ldap non disponibile'))
            return

        server_uri = os.getenv('LDAP_SERVER_URI', '').strip()
        bind_dn = os.getenv('LDAP_BIND_DN', '').strip()
        bind_password = os.getenv('LDAP_BIND_PASSWORD', '')
        base_dn = (options.get('base_dn') or '').strip()
        ldap_filter = (options.get('ldap_filter') or '').strip()
        dry_run = bool(options.get('dry_run'))

        if not server_uri:
            self.stderr.write(self.style.ERROR('LDAP_SERVER_URI non configurato'))
            return
        if not base_dn:
            self.stderr.write(self.style.ERROR('LDAP_USER_BASE_DN (o --base-dn) non configurato'))
            return
        if not ldap_filter:
            self.stderr.write(self.style.ERROR('Filtro LDAP vuoto'))
            return

        attr_username = os.getenv('LDAP_ATTR_USERNAME', 'uid')
        attr_first_name = os.getenv('LDAP_ATTR_FIRST_NAME', 'givenName')
        attr_last_name = os.getenv('LDAP_ATTR_LAST_NAME', 'sn')
        attr_email = os.getenv('LDAP_ATTR_EMAIL', 'mail')
        attr_department = os.getenv('LDAP_ATTR_DEPARTMENT', 'ou')

        attrs = [attr_username, attr_first_name, attr_last_name, attr_email, attr_department]

        conn = ldap.initialize(server_uri)
        conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)

        try:
            if bind_dn:
                conn.simple_bind_s(bind_dn, bind_password)
            else:
                conn.simple_bind_s()

            results = conn.search_s(base_dn, ldap.SCOPE_SUBTREE, ldap_filter, attrs)
        except ldap.LDAPError as exc:
            self.stderr.write(self.style.ERROR(f'Errore LDAP: {exc}'))
            return
        finally:
            try:
                conn.unbind_s()
            except Exception:
                pass

        created = 0
        updated = 0
        skipped = 0
        invalid_site = 0

        with transaction.atomic():
            for dn, entry in results:
                if not dn or not entry:
                    continue

                username = self._decode_first(entry.get(attr_username))
                if not username:
                    skipped += 1
                    continue

                first_name = self._decode_first(entry.get(attr_first_name))
                last_name = self._decode_first(entry.get(attr_last_name))
                email = self._decode_first(entry.get(attr_email))
                raw_department = self._decode_first(entry.get(attr_department))
                department = self._normalize_site(raw_department)
                if raw_department and not department:
                    invalid_site += 1

                user, was_created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        'first_name': first_name,
                        'last_name': last_name,
                        'email': email,
                        'department': department,
                        'role': User.Role.EMPLOYEE,
                        'is_active': False,
                    },
                )

                if was_created:
                    user.set_unusable_password()
                    if not dry_run:
                        user.save()
                    created += 1
                    continue

                user.first_name = first_name
                user.last_name = last_name
                user.email = email
                user.department = department
                user.is_active = False
                # Per utenti gestiti via LDAP non manteniamo password locale utilizzabile.
                user.set_unusable_password()
                if not dry_run:
                    user.save(update_fields=['first_name', 'last_name', 'email', 'department', 'is_active', 'password'])
                updated += 1

            if dry_run:
                transaction.set_rollback(True)

        suffix = ' (dry-run, nessuna modifica salvata)' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                f'Import LDAP completato: creati={created}, aggiornati={updated}, saltati={skipped}, sedi_non_valide={invalid_site}{suffix}'
            )
        )
