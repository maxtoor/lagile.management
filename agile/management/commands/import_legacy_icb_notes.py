import csv
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from agile.models import AuditLog, PlanDay, SITE_CHOICES, User


class Command(BaseCommand):
    help = (
        'Importa le descrizioni attivita dal leaves report legacy ICB e le copia in PlanDay.notes '
        'per i giorni REMOTE gia presenti.'
    )

    def add_arguments(self, parser):
        parser.add_argument('csv_path', help='Percorso del CSV legacy leaves report')
        parser.add_argument(
            '--backup-csv-path',
            default='',
            help='Percorso opzionale del backup CSV ICB completo da usare come mappa nome->email',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula l’import senza salvare modifiche nel database',
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Sovrascrive anche note gia valorizzate se diverse dal contenuto legacy',
        )

    @staticmethod
    def _norm(value: str) -> str:
        return str(value or '').strip()

    @staticmethod
    def _fold(value: str) -> str:
        text = str(value or '').strip().lower()
        if not text:
            return ''
        normalized = unicodedata.normalize('NFKD', text)
        return ''.join(ch for ch in normalized if not unicodedata.combining(ch))

    @staticmethod
    def _parse_iso_date(raw: str) -> date:
        return datetime.strptime(raw.strip(), '%Y-%m-%d').date()

    @staticmethod
    def _iter_days(start: date, end: date):
        current = start
        while current <= end:
            yield current
            current += timedelta(days=1)

    @staticmethod
    def _department_aliases() -> dict[str, str]:
        aliases = {}
        for site, _ in SITE_CHOICES:
            aliases[site.lower()] = site
        return aliases

    @classmethod
    def _normalize_department(cls, raw_value: str) -> str:
        raw = cls._norm(raw_value)
        if not raw:
            return ''
        aliases = cls._department_aliases()
        if raw.lower() in aliases:
            return aliases[raw.lower()]
        parts = [part.strip(" ,;:.()[]{}") for part in raw.split()]
        parts = [part for part in parts if part]
        if not parts:
            return ''
        last_word = parts[-1].lower()
        return aliases.get(last_word, '')

    def _load_rows(self, csv_path: Path) -> list[dict]:
        if not csv_path.exists():
            raise CommandError(f'File non trovato: {csv_path}')
        try:
            with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
        except OSError as exc:
            raise CommandError(f'Impossibile leggere il file CSV: {exc}') from exc

        if not rows:
            raise CommandError('CSV vuoto')
        required = {'Employee', 'Department', 'Leave Type', 'From', 'To', 'Comment'}
        if not required.issubset(set(rows[0].keys())):
            raise CommandError('Formato CSV non valido: colonne richieste mancanti')
        return rows

    def _load_backup_email_map(self, csv_path: Path) -> dict[tuple[str, str], set[str]]:
        if not csv_path.exists():
            raise CommandError(f'File backup CSV non trovato: {csv_path}')
        try:
            with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
                reader = csv.reader(handle)
                rows = list(reader)
        except OSError as exc:
            raise CommandError(f'Impossibile leggere il backup CSV: {exc}') from exc

        mapping: dict[tuple[str, str], set[str]] = defaultdict(set)
        for row in rows[1:]:
            if len(row) < 4:
                continue
            last_name = self._norm(row[1])
            first_name = self._norm(row[2])
            email = self._norm(row[3]).lower()
            department = self._normalize_department(row[0])
            if not last_name or not first_name or not email:
                continue
            full_name = self._fold(f'{first_name} {last_name}')
            mapping[(full_name, department.lower())].add(email)
        return mapping

    def _resolve_user(
        self,
        *,
        employee_name: str,
        department_name: str,
        users_by_full_name: dict[str, list[User]],
        users_by_email: dict[str, User],
        users_by_username: dict[str, User],
        backup_email_map: dict[tuple[str, str], set[str]],
    ) -> tuple[User | None, str]:
        folded_name = self._fold(employee_name)
        normalized_department = self._normalize_department(department_name)
        if not folded_name:
            return None, ''
        matches = users_by_full_name.get(folded_name, [])
        if not matches:
            mapped_emails = backup_email_map.get((folded_name, normalized_department.lower()), set())
            if len(mapped_emails) == 1:
                legacy_email = next(iter(mapped_emails))
                user = users_by_email.get(legacy_email)
                if user:
                    return user, 'backup_email'
                username_from_email = legacy_email.split('@', 1)[0].strip().lower()
                user = users_by_username.get(username_from_email)
                if user:
                    return user, 'backup_username_from_email'
            parts = [part for part in employee_name.split() if part.strip()]
            raw_firstname = parts[0] if parts else ''
            raw_lastname = parts[-1] if len(parts) >= 2 else ''
            folded_lastname = self._fold(raw_lastname)
            folded_firstname = self._fold(raw_firstname)

            if folded_lastname:
                surname_matches = [
                    user for user in users_by_username.values()
                    if self._fold(user.last_name) == folded_lastname
                ]
                unique_surname_matches = list({user.id: user for user in surname_matches}.values())
                if len(unique_surname_matches) == 1:
                    return unique_surname_matches[0], 'lastname'
                if len(unique_surname_matches) > 1 and folded_firstname:
                    narrowed = [
                        user for user in unique_surname_matches if self._fold(user.first_name) == folded_firstname
                    ]
                    if len(narrowed) == 1:
                        return narrowed[0], 'lastname_firstname'

                backup_email_matches = []
                for (mapped_name, mapped_department), emails in backup_email_map.items():
                    if normalized_department and mapped_department != normalized_department.lower():
                        continue
                    if not emails:
                        continue
                    if folded_lastname not in mapped_name:
                        continue
                    for email in emails:
                        user = users_by_email.get(email) or users_by_username.get(email.split('@', 1)[0].strip().lower())
                        if user:
                            backup_email_matches.append(user)
                unique_backup_matches = list({user.id: user for user in backup_email_matches}.values())
                if len(unique_backup_matches) == 1:
                    return unique_backup_matches[0], 'lastname_in_backup_email'
                if len(unique_backup_matches) > 1 and folded_firstname:
                    narrowed = [
                        user for user in unique_backup_matches if self._fold(user.first_name) == folded_firstname
                    ]
                    if len(narrowed) == 1:
                        return narrowed[0], 'lastname_in_backup_email_firstname'

            return None, ''
        if len(matches) == 1:
            return matches[0], 'full_name'

        if normalized_department:
            narrowed = [
                user for user in matches if (user.department or '').strip().lower() == normalized_department.lower()
            ]
            if len(narrowed) == 1:
                return narrowed[0], 'full_name_department'

        return None, 'ambiguous'

    def handle(self, *args, **options):
        csv_path = Path(options['csv_path']).expanduser()
        backup_csv_path_raw = str(options.get('backup_csv_path') or '').strip()
        dry_run = bool(options.get('dry_run'))
        overwrite = bool(options.get('overwrite'))
        today = timezone.localdate()
        current_month_start = today.replace(day=1)

        rows = self._load_rows(csv_path)
        users = list(User.objects.only('id', 'username', 'first_name', 'last_name', 'department'))
        users_by_email = {
            (user.email or '').strip().lower(): user
            for user in User.objects.exclude(email__isnull=True).exclude(email__exact='').only('id', 'username', 'email')
        }
        users_by_username = {
            (user.username or '').strip().lower(): user
            for user in User.objects.only('id', 'username')
        }
        users_by_full_name: dict[str, list[User]] = defaultdict(list)
        for user in users:
            full_name = f'{(user.first_name or "").strip()} {(user.last_name or "").strip()}'.strip()
            folded = self._fold(full_name)
            if folded:
                users_by_full_name[folded].append(user)
        backup_email_map: dict[tuple[str, str], set[str]] = {}
        if backup_csv_path_raw:
            backup_email_map = self._load_backup_email_map(Path(backup_csv_path_raw).expanduser())

        counters = {
            'rows_total': len(rows),
            'rows_programmazione': 0,
            'rows_comment_empty': 0,
            'rows_invalid': 0,
            'rows_user_missing': 0,
            'rows_user_ambiguous': 0,
            'days_current_or_future_skipped': 0,
            'plan_days_missing': 0,
            'plan_days_updated': 0,
            'plan_days_unchanged': 0,
            'plan_days_conflict_skipped': 0,
            'match_full_name': 0,
            'match_full_name_department': 0,
            'match_backup_email': 0,
            'match_backup_username_from_email': 0,
            'match_lastname': 0,
            'match_lastname_firstname': 0,
            'match_lastname_in_backup_email': 0,
            'match_lastname_in_backup_email_firstname': 0,
        }

        comments_by_user_day: dict[tuple[int, date], list[str]] = defaultdict(list)
        for row_index, row in enumerate(rows, start=2):
            leave_type = self._norm(row.get('Leave Type'))
            if leave_type != 'Programmazione':
                continue
            counters['rows_programmazione'] += 1

            comment = self._norm(row.get('Comment'))
            if not comment:
                counters['rows_comment_empty'] += 1
                continue

            employee_name = self._norm(row.get('Employee'))
            department_name = self._norm(row.get('Department'))
            user, match_kind = self._resolve_user(
                employee_name=employee_name,
                department_name=department_name,
                users_by_full_name=users_by_full_name,
                users_by_email=users_by_email,
                users_by_username=users_by_username,
                backup_email_map=backup_email_map,
            )
            if not user:
                if match_kind == 'ambiguous':
                    counters['rows_user_ambiguous'] += 1
                else:
                    counters['rows_user_missing'] += 1
                continue
            counters[f'match_{match_kind}'] += 1

            try:
                start_day = self._parse_iso_date(self._norm(row.get('From')))
                end_day = self._parse_iso_date(self._norm(row.get('To')))
            except ValueError:
                counters['rows_invalid'] += 1
                self.stderr.write(self.style.WARNING(f'Riga {row_index}: date non valide, record saltato'))
                continue
            if end_day < start_day:
                counters['rows_invalid'] += 1
                self.stderr.write(self.style.WARNING(f'Riga {row_index}: intervallo date invertito, record saltato'))
                continue

            for legacy_day in self._iter_days(start_day, end_day):
                if legacy_day >= current_month_start:
                    counters['days_current_or_future_skipped'] += 1
                    continue
                comments_by_user_day[(user.id, legacy_day)].append(comment)

        plan_days = {
            (plan_day.plan.user_id, plan_day.day): plan_day
            for plan_day in PlanDay.objects.select_related('plan')
            .filter(work_type=PlanDay.WorkType.REMOTE)
            .only('id', 'day', 'notes', 'plan__user_id', 'plan_id')
        }
        touched_plans: dict[int, int] = defaultdict(int)

        try:
            with transaction.atomic():
                for (user_id, work_day), comments in sorted(comments_by_user_day.items(), key=lambda item: (item[0][0], item[0][1])):
                    plan_day = plan_days.get((user_id, work_day))
                    if not plan_day:
                        counters['plan_days_missing'] += 1
                        continue

                    new_notes = '\n\n'.join(dict.fromkeys(comment for comment in comments if comment))
                    if not new_notes:
                        counters['plan_days_unchanged'] += 1
                        continue

                    current_notes = (plan_day.notes or '').strip()
                    if current_notes == new_notes:
                        counters['plan_days_unchanged'] += 1
                        continue
                    if current_notes and not overwrite:
                        counters['plan_days_conflict_skipped'] += 1
                        continue

                    plan_day.notes = new_notes
                    if not dry_run:
                        plan_day.save(update_fields=['notes'])
                    counters['plan_days_updated'] += 1
                    touched_plans[plan_day.plan_id] += 1

                if not dry_run:
                    for plan_id, days_updated in touched_plans.items():
                        AuditLog.track(
                            actor=None,
                            action='legacy_icb_notes_imported',
                            target_type='MonthlyPlan',
                            target_id=plan_id,
                            metadata={
                                'source_file': str(csv_path),
                                'days_updated': days_updated,
                            },
                        )

                if dry_run:
                    transaction.set_rollback(True)
        except Exception as exc:
            raise CommandError(f'Import note legacy fallito: {exc}') from exc

        suffix = ' (dry-run, nessuna modifica salvata)' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                'Import note legacy ICB completato'
                f'{suffix}: righe={counters["rows_total"]}, '
                f'programmazione={counters["rows_programmazione"]}, '
                f'giorni_aggiornati={counters["plan_days_updated"]}, '
                f'giorni_non_trovati={counters["plan_days_missing"]}'
            )
        )
        self.stdout.write(
            'Dettaglio: '
            f'commenti_vuoti={counters["rows_comment_empty"]}, '
            f'utenti_non_trovati={counters["rows_user_missing"]}, '
            f'utenti_ambigui={counters["rows_user_ambiguous"]}, '
            f'righe_non_valide={counters["rows_invalid"]}, '
            f'corrente_futuro={counters["days_current_or_future_skipped"]}, '
            f'giorni_invariati={counters["plan_days_unchanged"]}, '
            f'conflitti_note={counters["plan_days_conflict_skipped"]}'
        )
        self.stdout.write(
            'Match utenti: '
            f'nome_completo={counters["match_full_name"]}, '
            f'nome_completo_afferenza={counters["match_full_name_department"]}, '
            f'backup_email={counters["match_backup_email"]}, '
            f'backup_username_da_email={counters["match_backup_username_from_email"]}, '
            f'cognome={counters["match_lastname"]}, '
            f'cognome_nome={counters["match_lastname_firstname"]}, '
            f'cognome_in_backup_email={counters["match_lastname_in_backup_email"]}, '
            f'cognome_in_backup_email_nome={counters["match_lastname_in_backup_email_firstname"]}'
        )
