import csv
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
import unicodedata

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from agile.models import AuditLog, MonthlyPlan, PlanDay, User


@dataclass
class PlanImportBucket:
    user: User
    year: int
    month: int
    days: set[date] = field(default_factory=set)


class Command(BaseCommand):
    help = (
        'Importa lo storico Programmazione dal CSV legacy ICB in MonthlyPlan/PlanDay. '
        'Importa solo mesi passati, filtra weekend/festivita e salta i piani gia esistenti.'
    )

    def add_arguments(self, parser):
        parser.add_argument('csv_path', help='Percorso del CSV legacy ICB_backup.csv')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula l’import senza salvare modifiche nel database',
        )
        parser.add_argument(
            '--email',
            dest='email_filter',
            default='',
            help='Importa solo le righe relative a una specifica email utente',
        )

    @staticmethod
    def _parse_legacy_date(raw: str) -> date:
        return datetime.strptime(raw.strip(), '%d/%m/%Y').date()

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
    def _username_from_email(raw_email: str) -> str:
        email = str(raw_email or '').strip().lower()
        if '@' not in email:
            return ''
        return email.split('@', 1)[0].strip()

    @staticmethod
    def _iter_days(start: date, end: date):
        current = start
        while current <= end:
            yield current
            current += timedelta(days=1)

    @staticmethod
    def _plan_key(*, user_id: int, year: int, month: int) -> tuple[int, int, int]:
        return user_id, year, month

    @staticmethod
    def _load_rows(csv_path: Path) -> list[list[str]]:
        if not csv_path.exists():
            raise CommandError(f'File non trovato: {csv_path}')
        try:
            with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
                reader = csv.reader(handle)
                rows = list(reader)
        except OSError as exc:
            raise CommandError(f'Impossibile leggere il file CSV: {exc}') from exc

        if not rows:
            raise CommandError('CSV vuoto')
        if len(rows[0]) < 9:
            raise CommandError('Formato CSV non valido: intestazione incompleta')
        return rows

    def _resolve_user(
        self,
        *,
        raw_email: str,
        raw_firstname: str,
        raw_lastname: str,
        users: list[User],
    ) -> tuple[User | None, str]:
        email = self._norm(raw_email).lower()
        if email:
            email_matches = [user for user in users if (user.email or '').strip().lower() == email]
            if len(email_matches) == 1:
                return email_matches[0], 'email'

            username_from_email = self._username_from_email(email)
            if username_from_email:
                username_matches = [
                    user
                    for user in users
                    if (user.username or '').strip().lower() == username_from_email
                ]
                if len(username_matches) == 1:
                    return username_matches[0], 'username_from_email'

        folded_lastname = self._fold(raw_lastname)
        folded_firstname = self._fold(raw_firstname)
        if folded_lastname:
            surname_matches = [
                user for user in users if self._fold(user.last_name) == folded_lastname
            ]
            if len(surname_matches) == 1:
                return surname_matches[0], 'lastname'
            if len(surname_matches) > 1 and folded_firstname:
                narrowed = [
                    user for user in surname_matches if self._fold(user.first_name) == folded_firstname
                ]
                if len(narrowed) == 1:
                    return narrowed[0], 'lastname_firstname'

            email_contains_matches = [
                user
                for user in users
                if folded_lastname and folded_lastname in self._fold(user.email)
            ]
            if len(email_contains_matches) == 1:
                return email_contains_matches[0], 'lastname_in_email'
            if len(email_contains_matches) > 1 and folded_firstname:
                narrowed = [
                    user
                    for user in email_contains_matches
                    if self._fold(user.first_name) == folded_firstname
                ]
                if len(narrowed) == 1:
                    return narrowed[0], 'lastname_in_email_firstname'

        return None, ''

    def handle(self, *args, **options):
        csv_path = Path(options['csv_path']).expanduser()
        dry_run = bool(options.get('dry_run'))
        email_filter = str(options.get('email_filter') or '').strip().lower()

        rows = self._load_rows(csv_path)
        header, data_rows = rows[0], rows[1:]
        if header[:9] != [
            'Gruppo',
            'Cognome',
            'Nome',
            'Email',
            'Tipo',
            'Started at',
            'Date type',
            'Ended at',
            'Date type',
        ]:
            self.stdout.write(self.style.WARNING('Intestazione CSV non standard, procedo per posizione colonne'))

        today = timezone.localdate()
        current_month_start = today.replace(day=1)
        users = list(
            User.objects.only('id', 'username', 'email', 'first_name', 'last_name', 'department')
        )

        counters = {
            'rows_total': len(data_rows),
            'rows_programmazione': 0,
            'rows_variazione_ignored': 0,
            'rows_other_ignored': 0,
            'rows_email_filtered': 0,
            'rows_invalid': 0,
            'users_missing': 0,
            'match_email': 0,
            'match_username_from_email': 0,
            'match_lastname': 0,
            'match_lastname_firstname': 0,
            'match_lastname_in_email': 0,
            'match_lastname_in_email_firstname': 0,
            'plans_existing_skipped': 0,
            'plans_created': 0,
            'days_imported': 0,
            'days_weekend_skipped': 0,
            'days_holiday_skipped': 0,
            'days_current_or_future_skipped': 0,
            'rows_no_usable_past_days': 0,
        }
        missing_emails: set[str] = set()
        grouped: dict[tuple[int, int, int], PlanImportBucket] = {}

        for row_index, row in enumerate(data_rows, start=2):
            if len(row) < 9:
                counters['rows_invalid'] += 1
                self.stderr.write(self.style.WARNING(f'Riga {row_index}: colonne insufficienti, record saltato'))
                continue

            raw_lastname = self._norm(row[1])
            raw_firstname = self._norm(row[2])
            email = self._norm(row[3]).lower()
            leave_type = (row[4] or '').strip()
            if email_filter and email != email_filter:
                counters['rows_email_filtered'] += 1
                continue

            if leave_type == 'Variazione':
                counters['rows_variazione_ignored'] += 1
                continue
            if leave_type != 'Programmazione':
                counters['rows_other_ignored'] += 1
                continue

            counters['rows_programmazione'] += 1
            user, match_kind = self._resolve_user(
                raw_email=email,
                raw_firstname=raw_firstname,
                raw_lastname=raw_lastname,
                users=users,
            )
            if not user:
                counters['users_missing'] += 1
                missing_emails.add(email or f'<vuota-riga-{row_index}>')
                continue
            if match_kind:
                counters[f'match_{match_kind}'] += 1

            try:
                start_day = self._parse_legacy_date(row[5])
                end_day = self._parse_legacy_date(row[7])
            except ValueError:
                counters['rows_invalid'] += 1
                self.stderr.write(self.style.WARNING(f'Riga {row_index}: date non valide, record saltato'))
                continue

            if end_day < start_day:
                counters['rows_invalid'] += 1
                self.stderr.write(self.style.WARNING(f'Riga {row_index}: intervallo date invertito, record saltato'))
                continue

            usable_past_days = 0
            holiday_cache: dict[tuple[int, int, str], set[date]] = {}
            for legacy_day in self._iter_days(start_day, end_day):
                if legacy_day >= current_month_start:
                    counters['days_current_or_future_skipped'] += 1
                    continue
                if legacy_day.weekday() >= 5:
                    counters['days_weekend_skipped'] += 1
                    continue

                cache_key = (legacy_day.year, legacy_day.month, user.department or '')
                if cache_key not in holiday_cache:
                    holiday_cache[cache_key] = MonthlyPlan.holiday_days_for_month(
                        year=legacy_day.year,
                        month=legacy_day.month,
                        department=user.department or '',
                    )
                if legacy_day in holiday_cache[cache_key]:
                    counters['days_holiday_skipped'] += 1
                    continue

                key = self._plan_key(user_id=user.id, year=legacy_day.year, month=legacy_day.month)
                bucket = grouped.get(key)
                if not bucket:
                    bucket = PlanImportBucket(user=user, year=legacy_day.year, month=legacy_day.month)
                    grouped[key] = bucket
                bucket.days.add(legacy_day)
                usable_past_days += 1

            if usable_past_days == 0:
                counters['rows_no_usable_past_days'] += 1

        existing_plan_keys = {
            self._plan_key(user_id=plan.user_id, year=plan.year, month=plan.month)
            for plan in MonthlyPlan.objects.filter(
                user_id__in=[bucket.user.id for bucket in grouped.values()]
            ).only('user_id', 'year', 'month')
        }

        try:
            with transaction.atomic():
                for key, bucket in sorted(
                    grouped.items(),
                    key=lambda item: (item[1].user.username, item[1].year, item[1].month),
                ):
                    if not bucket.days:
                        continue
                    if key in existing_plan_keys:
                        counters['plans_existing_skipped'] += 1
                        continue

                    if dry_run:
                        counters['plans_created'] += 1
                        counters['days_imported'] += len(bucket.days)
                        continue

                    now = timezone.now()
                    plan = MonthlyPlan.objects.create(
                        user=bucket.user,
                        year=bucket.year,
                        month=bucket.month,
                        status=MonthlyPlan.Status.APPROVED,
                        submitted_at=now,
                        approved_at=now,
                    )
                    PlanDay.objects.bulk_create(
                        [
                            PlanDay(
                                plan=plan,
                                day=day_value,
                                work_type=PlanDay.WorkType.REMOTE,
                                notes='',
                            )
                            for day_value in sorted(bucket.days)
                        ]
                    )
                    plan.capture_approved_snapshot()
                    AuditLog.track(
                        actor=None,
                        action='legacy_icb_backup_imported',
                        target_type='MonthlyPlan',
                        target_id=plan.id,
                        metadata={
                            'source_file': str(csv_path),
                            'username': bucket.user.username,
                            'email': bucket.user.email or '',
                            'year': bucket.year,
                            'month': bucket.month,
                            'days_imported': len(bucket.days),
                        },
                    )
                    counters['plans_created'] += 1
                    counters['days_imported'] += len(bucket.days)

                if dry_run:
                    transaction.set_rollback(True)
        except Exception as exc:
            raise CommandError(f'Import fallito: {exc}') from exc

        suffix = ' (dry-run, nessuna modifica salvata)' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                'Import storico ICB completato'
                f'{suffix}: righe={counters["rows_total"]}, '
                f'programmazione={counters["rows_programmazione"]}, '
                f'piani creati={counters["plans_created"]}, '
                f'piani esistenti saltati={counters["plans_existing_skipped"]}, '
                f'giorni importati={counters["days_imported"]}'
            )
        )
        self.stdout.write(
            'Dettaglio skip: '
            f'variazioni ignorate={counters["rows_variazione_ignored"]}, '
            f'altro ignorato={counters["rows_other_ignored"]}, '
            f'utente mancante={counters["users_missing"]}, '
            f'righe non valide={counters["rows_invalid"]}, '
            f'weekend={counters["days_weekend_skipped"]}, '
            f'festivita={counters["days_holiday_skipped"]}, '
            f'corrente/futuro={counters["days_current_or_future_skipped"]}, '
            f'righe senza giorni utili={counters["rows_no_usable_past_days"]}'
        )
        self.stdout.write(
            'Match utenti: '
            f'email={counters["match_email"]}, '
            f'username_da_email={counters["match_username_from_email"]}, '
            f'cognome={counters["match_lastname"]}, '
            f'cognome_nome={counters["match_lastname_firstname"]}, '
            f'cognome_in_email={counters["match_lastname_in_email"]}, '
            f'cognome_in_email_nome={counters["match_lastname_in_email_firstname"]}'
        )
        if email_filter:
            self.stdout.write(f'Filtro email applicato: {email_filter}')
        if missing_emails:
            preview = ', '.join(sorted(missing_emails)[:10])
            tail = '' if len(missing_emails) <= 10 else f' ... (+{len(missing_emails) - 10})'
            self.stdout.write(self.style.WARNING(f'Email senza utente locale corrispondente: {preview}{tail}'))
