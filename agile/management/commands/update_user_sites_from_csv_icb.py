from __future__ import annotations

import csv
import os
import unicodedata
from typing import Optional

from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth.models import Group

from agile.models import SITE_CHOICES, User


class Command(BaseCommand):
    help = (
        'Versione ICB: aggiorna la sede utenti leggendo un CSV; '
        'se l\'utente non esiste in locale viene creato automaticamente.'
    )
    SITE_MANAGER_RULES = {
        'Napoli': {'username': 'direttore', 'auto_approve': True},
        'Catania': {'username': 'nicola.dantona', 'auto_approve': False},
        'Sassari': {'username': 'pietro.spanu', 'full_name': 'Pietro Spanu', 'auto_approve': False},
        'Padova': {'username': 'paolo.ruzza', 'full_name': 'Paolo ruzza', 'auto_approve': False},
    }

    def add_arguments(self, parser):
        parser.add_argument('csv_path', help='Percorso del file CSV')
        parser.add_argument(
            '--email-column',
            default='email',
            help='Nome colonna email nel CSV (default: email)',
        )
        parser.add_argument(
            '--site-column',
            default='sede',
            help='Nome colonna sede nel CSV (default: sede)',
        )
        parser.add_argument(
            '--site-mode',
            choices=('exact', 'last-word'),
            default='exact',
            help='Modalita lettura sede: exact=valore completo, last-word=ultima parola del campo (default: exact)',
        )
        parser.add_argument(
            '--import-groups',
            action='store_true',
            help='Importa anche i gruppi: usa la prima parola della colonna sede/department come nome gruppo',
        )
        parser.add_argument(
            '--fallback-lastname',
            action='store_true',
            help='Se email non disponibile/non trovata, prova il match su cognome (solo se univoco)',
        )
        parser.add_argument(
            '--lastname-column',
            default='lastname',
            help='Nome colonna cognome nel CSV per fallback (default: lastname)',
        )
        parser.add_argument(
            '--firstname-column',
            default='name',
            help='Nome colonna nome nel CSV per disambiguazione fallback (default: name)',
        )
        parser.add_argument(
            '--delimiter',
            default=',',
            help='Separatore CSV (default: ,). Esempio ";" per CSV italiani',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra il risultato senza salvare modifiche nel DB',
        )
        parser.add_argument(
            '--enrich-managers-from-csv',
            action='store_true',
            help='Aggiorna email/nome/cognome referenti usando le righe Default del CSV (default: disattivato, preferire LDAP)',
        )
        parser.add_argument(
            '--with-ldap-sync',
            action='store_true',
            help='Al termine esegue anche sync_ldap_users per aggiornare nome/cognome/email da LDAP',
        )

    @staticmethod
    def _norm(value) -> str:
        return str(value or '').strip()

    @staticmethod
    def _site_aliases():
        allowed = [choice[0] for choice in SITE_CHOICES]
        return {site.lower(): site for site in allowed}

    @staticmethod
    def _last_word(value: str) -> str:
        chunks = [part.strip(" ,;:.()[]{}") for part in str(value or '').split()]
        chunks = [part for part in chunks if part]
        return chunks[-1] if chunks else ''

    @staticmethod
    def _first_word(value: str) -> str:
        chunks = [part.strip(" ,;:.()[]{}") for part in str(value or '').split()]
        chunks = [part for part in chunks if part]
        return chunks[0] if chunks else ''

    @staticmethod
    def _fold(value: str) -> str:
        text = str(value or '').strip().lower()
        if not text:
            return ''
        normalized = unicodedata.normalize('NFKD', text)
        return ''.join(ch for ch in normalized if not unicodedata.combining(ch))

    @staticmethod
    def _username_from_email(raw_email: str) -> str:
        email = str(raw_email or '').strip().lower()
        if '@' not in email:
            return ''
        local_part = email.split('@', 1)[0].strip()
        return local_part

    @staticmethod
    def _build_unique_username(base_username: str, users_cache: list[User]) -> str:
        base = (base_username or '').strip().lower()
        if not base:
            return ''
        existing = {str(item.username or '').strip().lower() for item in users_cache}
        if base not in existing:
            return base
        suffix = 1
        while True:
            candidate = f'{base}.{suffix}'
            if candidate not in existing:
                return candidate
            suffix += 1

    @classmethod
    def _resolve_manager_for_site(cls, site: str):
        rule = cls.SITE_MANAGER_RULES.get(site)
        if not rule:
            return None

        username = (rule.get('username') or '').strip()
        if username:
            manager = User.objects.filter(username__iexact=username).first()
            if manager:
                return manager

        full_name = (rule.get('full_name') or '').strip()
        if full_name:
            folded_target = cls._fold(full_name)
            if folded_target:
                for candidate in User.objects.all().only('id', 'first_name', 'last_name'):
                    candidate_name = cls._fold(f'{candidate.first_name} {candidate.last_name}')
                    if candidate_name == folded_target:
                        return candidate
        return None

    @classmethod
    def _ensure_manager_for_site(cls, site: str, *, dry_run: bool):
        manager = cls._resolve_manager_for_site(site)
        if manager:
            return manager, False

        rule = cls.SITE_MANAGER_RULES.get(site) or {}
        username = (rule.get('username') or '').strip().lower()
        full_name = (rule.get('full_name') or '').strip()
        if not username and full_name:
            parts = [piece.strip().lower() for piece in full_name.split() if piece.strip()]
            if len(parts) >= 2:
                username = f'{parts[0]}.{parts[-1]}'
            elif parts:
                username = parts[0]
        if not username:
            return None, False

        first_name = ''
        last_name = ''
        if full_name:
            chunks = [piece.strip() for piece in full_name.split() if piece.strip()]
            if chunks:
                first_name = chunks[0]
            if len(chunks) > 1:
                last_name = ' '.join(chunks[1:])

        manager = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            role=User.Role.ADMIN,
            is_active=True,
        )
        manager.set_unusable_password()
        if not dry_run:
            manager.save()
        return manager, True

    @classmethod
    def _manager_sites_by_username(cls) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for site, rule in cls.SITE_MANAGER_RULES.items():
            username = str((rule or {}).get('username') or '').strip().lower()
            if not username:
                continue
            out.setdefault(username, []).append(site)
        return out

    @staticmethod
    def _is_same_user(left: Optional[User], right: Optional[User]) -> bool:
        if not left or not right:
            return False
        if left.pk and right.pk:
            return left.pk == right.pk
        left_username = str(left.username or '').strip().lower()
        right_username = str(right.username or '').strip().lower()
        return bool(left_username and right_username and left_username == right_username)

    @staticmethod
    def _user_manager_username(user: User) -> str:
        manager_obj = getattr(user, 'manager', None)
        if manager_obj:
            return str(manager_obj.username or '').strip().lower()
        manager_id = getattr(user, 'manager_id', None)
        if not manager_id:
            return ''
        manager = User.objects.filter(pk=manager_id).only('username').first()
        return str(manager.username or '').strip().lower() if manager else ''

    @classmethod
    def _has_same_manager(cls, user: User, manager_user: Optional[User]) -> bool:
        current_manager_username = cls._user_manager_username(user)
        target_username = str(getattr(manager_user, 'username', '') or '').strip().lower()
        if not target_username:
            return not current_manager_username
        return current_manager_username == target_username

    @staticmethod
    def _decode_first(values):
        if not values:
            return ''
        value = values[0]
        if isinstance(value, bytes):
            return value.decode('utf-8', errors='ignore').strip()
        return str(value).strip()

    def _sync_ldap_inline(self, *, dry_run: bool) -> None:
        try:
            import ldap
        except ImportError:
            self.stderr.write(self.style.ERROR('Libreria python-ldap non disponibile: sync LDAP saltata'))
            return

        server_uri = os.getenv('LDAP_SERVER_URI', '').strip()
        bind_dn = os.getenv('LDAP_BIND_DN', '').strip()
        bind_password = os.getenv('LDAP_BIND_PASSWORD', '')
        base_dn = os.getenv('LDAP_USER_BASE_DN', '').strip()
        ldap_filter = os.getenv('LDAP_IMPORT_FILTER', '(objectClass=person)').strip()
        if not server_uri or not base_dn or not ldap_filter:
            self.stderr.write(self.style.ERROR('Configurazione LDAP incompleta: sync LDAP saltata'))
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
        seen_usernames: set[str] = set()
        for dn, entry in results:
            if not dn or not entry:
                continue
            username = self._decode_first(entry.get(attr_username))
            if not username or username in seen_usernames:
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

        ldap_email_counts: dict[str, int] = {}
        for row in ldap_rows:
            email = (row.get('email') or '').strip().lower()
            if not email:
                continue
            ldap_email_counts[email] = ldap_email_counts.get(email, 0) + 1

        updated = 0
        unchanged = 0
        skipped_local_password = 0
        skipped_missing_local = 0
        matched_by_email = 0
        ambiguous_email_matches = 0

        with transaction.atomic():
            for row in ldap_rows:
                username = row['username']
                user = User.objects.filter(username=username).first()
                email = (row.get('email') or '').strip()

                if user is None and email:
                    local_email_matches = list(User.objects.filter(email__iexact=email).exclude(username=username))
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

                if user is None:
                    skipped_missing_local += 1
                    continue

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

            if dry_run:
                transaction.set_rollback(True)

        suffix = ' (dry-run, nessuna modifica salvata)' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                'Sync LDAP inline completato: '
                f'ldap_righe={len(ldap_rows)}, aggiornati={updated}, invariati={unchanged}, '
                f'saltati_locali={skipped_local_password}, assenze_locali={skipped_missing_local}, '
                f'match_email={matched_by_email}, match_email_ambigui={ambiguous_email_matches}{suffix}'
            )
        )

    def handle(self, *args, **options):
        csv_path = self._norm(options.get('csv_path'))
        email_column = self._norm(options.get('email_column') or 'email')
        site_column = self._norm(options.get('site_column') or 'sede')
        site_mode = self._norm(options.get('site_mode') or 'exact')
        import_groups = bool(options.get('import_groups'))
        fallback_lastname = bool(options.get('fallback_lastname'))
        lastname_column = self._norm(options.get('lastname_column') or 'lastname')
        firstname_column = self._norm(options.get('firstname_column') or 'name')
        delimiter = str(options.get('delimiter') or ',')
        dry_run = bool(options.get('dry_run'))
        enrich_managers_from_csv = bool(options.get('enrich_managers_from_csv'))
        with_ldap_sync = bool(options.get('with_ldap_sync'))

        if not csv_path:
            self.stderr.write(self.style.ERROR('Percorso CSV non valido'))
            return
        if len(delimiter) != 1:
            self.stderr.write(self.style.ERROR('Il delimitatore deve essere un singolo carattere'))
            return

        allowed_sites_map = self._site_aliases()
        allowed_sites = list(allowed_sites_map.values())

        total = 0
        updated = 0
        unchanged = 0
        not_found = 0
        skipped = 0
        skipped_default = 0
        invalid_site = 0
        ambiguous_lastname_exact = 0
        ambiguous_lastname_email = 0
        groups_created = 0
        groups_assigned = 0
        groups_unchanged = 0
        groups_missing = 0
        users_created = 0
        managers_assigned = 0
        managers_not_found = 0
        managers_self_skipped = 0
        managers_role_promoted = 0
        managers_created = 0
        managers_enriched = 0
        dry_run_manager_cache: dict[str, User] = {}
        updated_usernames: list[str] = []
        created_usernames: list[str] = []
        not_found_refs: list[str] = []
        manager_sites_by_username = self._manager_sites_by_username()

        try:
            with open(csv_path, 'r', encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle, delimiter=delimiter, skipinitialspace=True)
                if not reader.fieldnames:
                    self.stderr.write(self.style.ERROR('CSV senza intestazioni'))
                    return

                fieldnames = [self._norm(name) for name in reader.fieldnames if name is not None]
                field_map = {name.lower(): name for name in fieldnames}
                email_key = field_map.get(email_column.lower())
                site_key = field_map.get(site_column.lower())
                lastname_key = field_map.get(lastname_column.lower())
                firstname_key = field_map.get(firstname_column.lower())
                missing_headers = []
                if not email_key:
                    missing_headers.append(email_column)
                if not site_key:
                    missing_headers.append(site_column)
                if fallback_lastname and not lastname_key:
                    missing_headers.append(lastname_column)
                if missing_headers:
                    self.stderr.write(
                        self.style.ERROR(
                            f'Intestazioni mancanti nel CSV: {", ".join(missing_headers)}. '
                            f'Intestazioni trovate: {", ".join(fieldnames)}'
                        )
                    )
                    return

                with transaction.atomic():
                    all_users = list(User.objects.all().only('id', 'username', 'email', 'first_name', 'last_name', 'department', 'aila_subscribed'))
                    for row in reader:
                        total += 1
                        row_index = total + 1  # include header line in numbering
                        raw_email = self._norm(row.get(email_key, '')).lower()
                        raw_lastname = self._norm(row.get(lastname_key, '')) if lastname_key else ''
                        raw_firstname = self._norm(row.get(firstname_key, '')) if firstname_key else ''
                        raw_site_input = self._norm(row.get(site_key, ''))
                        raw_site = raw_site_input if site_mode == 'exact' else self._last_word(raw_site_input)
                        raw_group = self._first_word(raw_site_input) if import_groups else ''

                        if not raw_site:
                            skipped += 1
                            self.stdout.write(
                                self.style.WARNING(
                                    f'Riga {row_index}: sede mancante (email="{raw_email}" cognome="{raw_lastname}" nome="{raw_firstname}")'
                                )
                            )
                            continue
                        if not raw_email and not (fallback_lastname and raw_lastname):
                            skipped += 1
                            self.stdout.write(
                                self.style.WARNING(
                                    f'Riga {row_index}: identificativo mancante (email/cognome) per sede "{raw_site_input}"'
                                )
                            )
                            continue
                        if 'default' in raw_site_input.lower():
                            skipped_default += 1
                            if enrich_managers_from_csv:
                                manager_username_from_email = self._username_from_email(raw_email)
                                manager_sites = manager_sites_by_username.get(manager_username_from_email, [])
                                for manager_site in manager_sites:
                                    manager_user = None
                                    manager_created = False
                                    if dry_run and manager_site in dry_run_manager_cache:
                                        manager_user = dry_run_manager_cache[manager_site]
                                    else:
                                        manager_user, manager_created = self._ensure_manager_for_site(manager_site, dry_run=dry_run)
                                        if dry_run and manager_user:
                                            dry_run_manager_cache[manager_site] = manager_user
                                    if not manager_user:
                                        continue
                                    if manager_created:
                                        managers_created += 1
                                        self.stdout.write(
                                            self.style.WARNING(
                                                f'Riga {row_index}: referente creato automaticamente "{manager_user.username}" per sede "{manager_site}"'
                                            )
                                        )
                                    changed_fields = []
                                    if raw_email and (manager_user.email or '').strip().lower() != raw_email:
                                        manager_user.email = raw_email
                                        changed_fields.append('email')
                                    if raw_firstname and (manager_user.first_name or '').strip() != raw_firstname:
                                        manager_user.first_name = raw_firstname
                                        changed_fields.append('nome')
                                    if raw_lastname and (manager_user.last_name or '').strip() != raw_lastname:
                                        manager_user.last_name = raw_lastname
                                        changed_fields.append('cognome')
                                    if manager_user.role not in {'ADMIN', 'SUPERADMIN'}:
                                        manager_user.role = User.Role.ADMIN
                                        changed_fields.append('ruolo')

                                    if changed_fields:
                                        managers_enriched += 1
                                        if not dry_run:
                                            manager_user.save(update_fields=['email', 'first_name', 'last_name', 'role', 'is_staff'])
                                        self.stdout.write(
                                            self.style.WARNING(
                                                f'Riga {row_index}: referente "{manager_user.username}" aggiornato ({", ".join(changed_fields)})'
                                            )
                                        )
                            # Con valore Default: non impostare afferenza territoriale,
                            # ma creare/aggiornare comunque l'utente locale.
                            user = None
                            if raw_email:
                                user = User.objects.filter(email__iexact=raw_email).first()
                                if user:
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Riga {row_index}: match per email "{raw_email}" -> utente "{user.username}" (Default)'
                                        )
                                    )
                                if not user:
                                    username_from_email = self._username_from_email(raw_email)
                                    if username_from_email:
                                        user = User.objects.filter(username__iexact=username_from_email).first()
                                        if user:
                                            self.stdout.write(
                                                self.style.WARNING(
                                                    f'Riga {row_index}: email non trovata, match username "{username_from_email}" '
                                                    f'-> utente "{user.username}" (Default)'
                                                )
                                            )
                            if not user and fallback_lastname and raw_lastname and not raw_email:
                                folded_lastname = self._fold(raw_lastname)
                                folded_firstname = self._fold(raw_firstname)
                                surname_candidates = [
                                    candidate
                                    for candidate in all_users
                                    if self._fold(candidate.last_name) == folded_lastname
                                ]
                                if len(surname_candidates) == 1:
                                    user = surname_candidates[0]
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Riga {row_index}: match cognome esatto "{raw_lastname}" -> utente "{user.username}" (Default)'
                                        )
                                    )
                                elif len(surname_candidates) > 1 and raw_firstname:
                                    narrowed_candidates = [
                                        candidate
                                        for candidate in surname_candidates
                                        if self._fold(candidate.first_name) == folded_firstname
                                    ]
                                    if len(narrowed_candidates) == 1:
                                        user = narrowed_candidates[0]
                                        self.stdout.write(
                                            self.style.WARNING(
                                                f'Riga {row_index}: cognome ambiguo risolto con nome "{raw_firstname}" -> utente "{user.username}" (Default)'
                                            )
                                        )
                            created_this_row = False
                            if not user:
                                base_username = self._username_from_email(raw_email)
                                username = self._build_unique_username(base_username, all_users)
                                if not username:
                                    not_found += 1
                                    ref = raw_email or raw_lastname or f'riga-{row_index}'
                                    not_found_refs.append(ref)
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Riga {row_index}: valore Default, utente non trovato e impossibile crearlo '
                                            f'(email="{raw_email}" cognome="{raw_lastname}" nome="{raw_firstname}")'
                                        )
                                    )
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Riga {row_index}: sede ignorata per valore Default (email="{raw_email}")'
                                        )
                                    )
                                    continue
                                user = User(
                                    username=username,
                                    email=raw_email,
                                    first_name=raw_firstname,
                                    last_name=raw_lastname,
                                    role=User.Role.EMPLOYEE,
                                    is_active=True,
                                )
                                user.set_unusable_password()
                                if not dry_run:
                                    user.save()
                                users_created += 1
                                created_usernames.append(user.username)
                                created_this_row = True
                                all_users.append(user)
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Riga {row_index}: utente creato automaticamente "{username}" da email "{raw_email}" (Default)'
                                    )
                                )

                            current_site = (user.department or '')
                            current_aila = bool(user.aila_subscribed)
                            current_active = bool(user.is_active)
                            current_auto_approve = bool(user.auto_approve)
                            current_has_manager = bool(user.manager_id)
                            if (
                                current_site == ''
                                and not current_aila
                                and current_active
                                and not current_auto_approve
                                and not current_has_manager
                            ):
                                unchanged += 1
                            else:
                                user.department = ''
                                user.aila_subscribed = False
                                user.is_active = True
                                user.auto_approve = False
                                user.manager = None
                                if not dry_run:
                                    user.save(update_fields=['department', 'aila_subscribed', 'is_active', 'auto_approve', 'manager'])
                                updated += 1
                                updated_usernames.append(user.username)

                            self.stdout.write(
                                self.style.WARNING(
                                    f'Riga {row_index}: sede ignorata per valore Default (email="{raw_email}")'
                                )
                            )
                            continue

                        normalized_site = allowed_sites_map.get(raw_site.lower())
                        if not normalized_site:
                            invalid_site += 1
                            self.stdout.write(
                                self.style.WARNING(
                                    f'Riga {row_index}: sede non valida "{raw_site}" per email "{raw_email}" '
                                    f'(valori ammessi: {", ".join(allowed_sites)})'
                                )
                            )
                            continue

                        user = None
                        # 1) email CSV == email DB
                        if raw_email:
                            user = User.objects.filter(email__iexact=raw_email).first()
                            if user:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Riga {row_index}: match per email "{raw_email}" -> utente "{user.username}"'
                                    )
                                )
                        if not user and raw_email:
                            username_from_email = self._username_from_email(raw_email)
                            if username_from_email:
                                user = User.objects.filter(username__iexact=username_from_email).first()
                                if user:
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Riga {row_index}: email non trovata, match username "{username_from_email}" '
                                            f'-> utente "{user.username}"'
                                        )
                                    )

                        # 2) email diversa/non trovata -> lastname CSV == lastname DB
                        folded_lastname = self._fold(raw_lastname)
                        folded_firstname = self._fold(raw_firstname)
                        if not user and fallback_lastname and raw_lastname:
                            surname_candidates = [
                                candidate
                                for candidate in all_users
                                if self._fold(candidate.last_name) == folded_lastname
                            ]
                            surname_count = len(surname_candidates)
                            if surname_count == 1:
                                user = surname_candidates[0]
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Riga {row_index}: email non trovata/diversa, match cognome esatto "{raw_lastname}" '
                                        f'-> utente "{user.username}"'
                                    )
                                )
                            elif surname_count > 1:
                                if raw_firstname:
                                    narrowed_candidates = [
                                        candidate
                                        for candidate in surname_candidates
                                        if self._fold(candidate.first_name) == folded_firstname
                                    ]
                                    narrowed_count = len(narrowed_candidates)
                                    if narrowed_count == 1:
                                        user = narrowed_candidates[0]
                                        self.stdout.write(
                                            self.style.WARNING(
                                                f'Riga {row_index}: cognome esatto ambiguo risolto con nome "{raw_firstname}" '
                                                f'-> utente "{user.username}"'
                                            )
                                        )
                                    else:
                                        ambiguous_lastname_exact += 1
                                        self.stdout.write(
                                            self.style.WARNING(
                                                f'Riga {row_index}: cognome esatto ambiguo "{raw_lastname}" '
                                                f'(utenti={surname_count}, nome="{raw_firstname}" match={narrowed_count}), '
                                                f'provo match su email DB contenente cognome'
                                            )
                                        )
                                else:
                                    ambiguous_lastname_exact += 1
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Riga {row_index}: cognome esatto ambiguo "{raw_lastname}" '
                                            f'({surname_count} utenti), provo match su email DB contenente cognome'
                                        )
                                    )

                        # 3) email diversa e cognome non uguale -> lastname CSV contenuto in email DB
                        if not user and fallback_lastname and raw_lastname:
                            email_contains_candidates = [
                                candidate
                                for candidate in all_users
                                if folded_lastname and folded_lastname in self._fold(candidate.email)
                            ]
                            email_contains_count = len(email_contains_candidates)
                            if email_contains_count == 1:
                                user = email_contains_candidates[0]
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Riga {row_index}: match cognome-in-email "{raw_lastname}" '
                                        f'-> utente "{user.username}"'
                                    )
                                )
                            elif email_contains_count > 1:
                                if raw_firstname:
                                    narrowed_candidates = [
                                        candidate
                                        for candidate in email_contains_candidates
                                        if self._fold(candidate.first_name) == folded_firstname
                                    ]
                                    narrowed_count = len(narrowed_candidates)
                                    if narrowed_count == 1:
                                        user = narrowed_candidates[0]
                                        self.stdout.write(
                                            self.style.WARNING(
                                                f'Riga {row_index}: match cognome-in-email ambiguo risolto con nome "{raw_firstname}" '
                                                f'-> utente "{user.username}"'
                                            )
                                        )
                                    else:
                                        ambiguous_lastname_email += 1
                                        self.stdout.write(
                                            self.style.WARNING(
                                                f'Riga {row_index}: match cognome-in-email ambiguo "{raw_lastname}" '
                                                f'(utenti={email_contains_count}, nome="{raw_firstname}" match={narrowed_count}), '
                                                f'riga ignorata'
                                            )
                                        )
                                        continue
                                else:
                                    ambiguous_lastname_email += 1
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Riga {row_index}: match cognome-in-email ambiguo "{raw_lastname}" '
                                            f'({email_contains_count} utenti), riga ignorata'
                                        )
                                    )
                                    continue

                        created_this_row = False
                        if not user:
                            base_username = self._username_from_email(raw_email)
                            username = self._build_unique_username(base_username, all_users)
                            if not username:
                                not_found += 1
                                ref = raw_email or raw_lastname or f'riga-{row_index}'
                                not_found_refs.append(ref)
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Riga {row_index}: utente non trovato e impossibile crearlo '
                                        f'(email="{raw_email}" cognome="{raw_lastname}" nome="{raw_firstname}")'
                                    )
                                )
                                continue

                            user = User(
                                username=username,
                                email=raw_email,
                                first_name=raw_firstname,
                                last_name=raw_lastname,
                                role=User.Role.EMPLOYEE,
                                is_active=True,
                            )
                            user.set_unusable_password()
                            if not dry_run:
                                user.save()
                            users_created += 1
                            created_usernames.append(user.username)
                            created_this_row = True
                            all_users.append(user)
                            self.stdout.write(
                                self.style.WARNING(
                                    f'Riga {row_index}: utente creato automaticamente '
                                    f'"{username}" da email "{raw_email}"'
                                )
                            )

                        current_site = (user.department or '')
                        current_aila = bool(user.aila_subscribed)
                        target_auto_approve = bool(self.SITE_MANAGER_RULES.get(normalized_site, {}).get('auto_approve', False))
                        manager_user = None
                        manager_created = False
                        if dry_run and normalized_site in dry_run_manager_cache:
                            manager_user = dry_run_manager_cache[normalized_site]
                        else:
                            manager_user, manager_created = self._ensure_manager_for_site(normalized_site, dry_run=dry_run)
                            if dry_run and manager_user:
                                dry_run_manager_cache[normalized_site] = manager_user
                        if manager_created:
                            managers_created += 1
                            self.stdout.write(
                                self.style.WARNING(
                                    f'Riga {row_index}: referente creato automaticamente "{manager_user.username}" per sede "{normalized_site}"'
                                )
                            )
                            if manager_user.pk:
                                all_users.append(manager_user)
                        manager_changed = False
                        manager_promoted = False
                        if manager_user:
                            if self._is_same_user(manager_user, user):
                                managers_self_skipped += 1
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Riga {row_index}: referente "{manager_user.username}" coincide con utente "{user.username}", referente non assegnato'
                                    )
                                )
                            else:
                                if not self._has_same_manager(user, manager_user):
                                    managers_assigned += 1
                                    manager_changed = True
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Riga {row_index}: referente impostato a "{manager_user.username}" per sede "{normalized_site}"'
                                        )
                                    )
                                user.manager = manager_user
                                if manager_user.role not in {'ADMIN', 'SUPERADMIN'}:
                                    manager_user.role = 'ADMIN'
                                    if not dry_run:
                                        manager_user.save(update_fields=['role', 'is_staff'])
                                    managers_role_promoted += 1
                                    manager_promoted = True
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Riga {row_index}: utente referente "{manager_user.username}" promosso a Responsabile approvazione'
                                        )
                                    )
                        else:
                            managers_not_found += 1
                            self.stdout.write(
                                self.style.WARNING(
                                    f'Riga {row_index}: referente non trovato per sede "{normalized_site}"'
                                )
                            )

                        if (
                            current_site == normalized_site
                            and current_aila
                            and bool(user.is_active)
                            and bool(user.auto_approve) == target_auto_approve
                            and not manager_changed
                            and not manager_promoted
                        ):
                            unchanged += 1
                        else:
                            user.department = normalized_site
                            user.aila_subscribed = True
                            user.is_active = True
                            user.auto_approve = target_auto_approve
                            if manager_user and not self._is_same_user(manager_user, user):
                                user.manager = manager_user
                            if not dry_run:
                                user.save(update_fields=['department', 'aila_subscribed', 'is_active', 'auto_approve', 'manager'])
                            updated += 1
                            updated_usernames.append(user.username)

                        if import_groups:
                            if dry_run and created_this_row and not getattr(user, 'pk', None):
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Riga {row_index}: dry-run su utente nuovo, associazione gruppo solo simulata'
                                    )
                                )
                                continue
                            if not raw_group or raw_group.lower() == 'default':
                                groups_missing += 1
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Riga {row_index}: gruppo non impostato (valore iniziale department="{raw_site_input}")'
                                    )
                                )
                            else:
                                group_obj, group_created = Group.objects.get_or_create(name=raw_group)
                                if group_created:
                                    groups_created += 1
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Riga {row_index}: creato gruppo "{group_obj.name}"'
                                        )
                                    )
                                else:
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Riga {row_index}: gruppo "{group_obj.name}" gia esistente'
                                        )
                                    )
                                if user.groups.filter(id=group_obj.id).exists():
                                    groups_unchanged += 1
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Riga {row_index}: utente "{user.username}" gia associato al gruppo "{group_obj.name}"'
                                        )
                                    )
                                else:
                                    user.groups.add(group_obj)
                                    groups_assigned += 1
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Riga {row_index}: associato utente "{user.username}" al gruppo "{group_obj.name}"'
                                        )
                                    )

                    if dry_run:
                        transaction.set_rollback(True)
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f'File non trovato: {csv_path}'))
            return
        except OSError as exc:
            self.stderr.write(self.style.ERROR(f'Errore lettura file CSV: {exc}'))
            return

        suffix = ' (dry-run, nessuna modifica salvata)' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                'Aggiornamento sedi da CSV completato: '
                f'righe={total}, aggiornati={updated}, invariati={unchanged}, '
                f'utenti_creati={users_created}, '
                f'utenti_non_trovati={not_found}, sede_non_valida={invalid_site}, '
                f'righe_default={skipped_default}, cognome_esatto_ambiguo={ambiguous_lastname_exact}, '
                f'cognome_in_email_ambiguo={ambiguous_lastname_email}, righe_saltate={skipped}, '
                f'gruppi_creati={groups_created}, gruppi_assegnati={groups_assigned}, '
                f'gruppi_gia_associati={groups_unchanged}, gruppo_mancante={groups_missing}, '
                f'referenti_impostati={managers_assigned}, referenti_non_trovati={managers_not_found}, '
                f'referenti_self_skipped={managers_self_skipped}, referenti_promossi_ruolo={managers_role_promoted}, '
                f'referenti_creati={managers_created}, referenti_arricchiti={managers_enriched}{suffix}'
            )
        )
        updated_list = ', '.join(sorted(set(updated_usernames))) or '-'
        created_list = ', '.join(sorted(set(created_usernames))) or '-'
        not_found_list = ', '.join(sorted(set(not_found_refs))) or '-'
        self.stdout.write(f'UTENTI_AGGIORNATI: {updated_list}')
        self.stdout.write(f'UTENTI_CREATI: {created_list}')
        self.stdout.write(f'UTENTI_NON_TROVATI: {not_found_list}')

        if with_ldap_sync:
            self.stdout.write('Avvio sincronizzazione LDAP inline post-import...')
            self._sync_ldap_inline(dry_run=dry_run)
