import os

from django.core.management.base import BaseCommand
from django.db import transaction

from agile.models import User


class Command(BaseCommand):
    help = (
        'Sincronizza gli utenti LDAP nel DB locale usando username come chiave. '
        'Aggiorna solo nome/cognome/email e non tocca campi applicativi (sede, referente, AILA, ruolo, auto-approve).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--filter',
            dest='ldap_filter',
            default=os.getenv('LDAP_IMPORT_FILTER', '(objectClass=person)'),
            help='Filtro LDAP per selezionare gli utenti da sincronizzare',
        )
        parser.add_argument(
            '--base-dn',
            dest='base_dn',
            default=os.getenv('LDAP_USER_BASE_DN', ''),
            help='Base DN per la ricerca LDAP (default: LDAP_USER_BASE_DN)',
        )
        parser.add_argument(
            '--deactivate-missing',
            action='store_true',
            help='Disattiva gli utenti LDAP locali non piu presenti in LDAP (solo account con password non utilizzabile).',
        )
        parser.add_argument(
            '--create-missing',
            action='store_true',
            help='Crea in locale gli utenti presenti in LDAP ma assenti nel DB (default: disattivo).',
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
        deactivate_missing = bool(options.get('deactivate_missing'))
        create_missing = bool(options.get('create_missing'))
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
        attrs = [attr_username, attr_first_name, attr_last_name, attr_email]

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

        ldap_rows = []
        duplicated_usernames = 0
        missing_username = 0
        seen_usernames: set[str] = set()
        for dn, entry in results:
            if not dn or not entry:
                continue
            username = self._decode_first(entry.get(attr_username))
            if not username:
                missing_username += 1
                continue
            if username in seen_usernames:
                duplicated_usernames += 1
                continue
            seen_usernames.add(username)
            ldap_rows.append(
                {
                    'username': username,
                    'first_name': self._decode_first(entry.get(attr_first_name)),
                    'last_name': self._decode_first(entry.get(attr_last_name)),
                    'email': self._decode_first(entry.get(attr_email)),
                }
            )

        ldap_usernames = {row['username'] for row in ldap_rows}
        ldap_email_counts: dict[str, int] = {}
        for row in ldap_rows:
            email = (row.get('email') or '').strip().lower()
            if not email:
                continue
            ldap_email_counts[email] = ldap_email_counts.get(email, 0) + 1

        created = 0
        updated = 0
        unchanged = 0
        skipped_local_password = 0
        skipped_missing_local = 0
        deactivated = 0
        potential_rename_matches = 0
        matched_by_email = 0
        ambiguous_email_matches = 0

        with transaction.atomic():
            for row in ldap_rows:
                username = row['username']
                user = User.objects.filter(username=username).first()
                email = (row.get('email') or '').strip()

                if user is None:
                    # Fallback su email: utile quando l'username locale non coincide ma l'account LDAP e lo stesso.
                    if email:
                        local_email_matches = list(
                            User.objects.filter(email__iexact=email).exclude(username=username)
                        )
                        if len(local_email_matches) == 1 and ldap_email_counts.get(email.lower(), 0) == 1:
                            candidate = local_email_matches[0]
                            if candidate.has_usable_password():
                                skipped_local_password += 1
                                continue
                            user = candidate
                            matched_by_email += 1
                        elif len(local_email_matches) > 1:
                            ambiguous_email_matches += 1
                            continue

                    if user is None and email and User.objects.filter(email__iexact=email).exclude(username=username).exists():
                        potential_rename_matches += 1

                    if user is None and not create_missing:
                        skipped_missing_local += 1
                        continue

                    if user is None:
                        user = User(
                            username=username,
                            first_name=row['first_name'],
                            last_name=row['last_name'],
                            email=email,
                            role=User.Role.EMPLOYEE,
                            is_active=False,
                        )
                        user.set_unusable_password()
                        if not dry_run:
                            user.save()
                        created += 1
                        continue

                # Se l'utente ha password locale utilizzabile, lo trattiamo come account locale e non lo tocchiamo.
                if user.has_usable_password():
                    skipped_local_password += 1
                    continue

                changed_fields = []
                for field in ('first_name', 'last_name', 'email'):
                    new_value = row[field]
                    if getattr(user, field) != new_value:
                        setattr(user, field, new_value)
                        changed_fields.append(field)

                if changed_fields:
                    if not dry_run:
                        user.save(update_fields=changed_fields)
                    updated += 1
                else:
                    unchanged += 1

            if deactivate_missing:
                missing_qs = User.objects.exclude(is_superuser=True).filter(
                    password__startswith='!'
                ).exclude(username__in=ldap_usernames)
                for user in missing_qs.only('id', 'is_active'):
                    if user.is_active:
                        user.is_active = False
                        if not dry_run:
                            user.save(update_fields=['is_active'])
                        deactivated += 1

            if dry_run:
                transaction.set_rollback(True)

        suffix = ' (dry-run, nessuna modifica salvata)' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                'Sync LDAP completato: '
                f'ldap_righe={len(ldap_rows)}, '
                f'creati={created}, aggiornati={updated}, invariati={unchanged}, '
                f'saltati_locali={skipped_local_password}, disattivati_assenti={deactivated}, '
                f'assenze_locali_non_create={skipped_missing_local}, '
                f'match_email={matched_by_email}, match_email_ambigui={ambiguous_email_matches}, '
                f'duplicati_username={duplicated_usernames}, senza_username={missing_username}, '
                f'possibili_rinomine={potential_rename_matches}'
                f'{suffix}'
            )
        )
