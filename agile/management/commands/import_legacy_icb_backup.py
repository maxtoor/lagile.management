import csv
from collections import defaultdict
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
    legacy_statuses: set[str] = field(default_factory=set)


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
        parser.add_argument(
            '--overwrite-existing',
            action='store_true',
            help='Sovrascrive i piani gia esistenti per gli stessi utente/mese',
        )
        parser.add_argument(
            '--leaves-report-csv',
            action='append',
            default=[],
            help='CSV legacy Leaves report da usare come sorgente status per mese corrente/prossimo (ripetibile)',
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

    def _load_leaves_report_status_map(self, csv_paths: list[str]) -> dict[tuple[str, str, date], set[str]]:
        status_map: dict[tuple[str, str, date], set[str]] = defaultdict(set)
        for raw_path in csv_paths:
            csv_path = Path(str(raw_path or '').strip()).expanduser()
            if not csv_path.exists():
                raise CommandError(f'Leaves report CSV non trovato: {csv_path}')
            try:
                with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
                    reader = csv.DictReader(handle)
                    rows = list(reader)
            except OSError as exc:
                raise CommandError(f'Impossibile leggere il leaves report CSV: {exc}') from exc

            required = {'Employee', 'Department', 'Leave Type', 'From', 'To', 'Status'}
            if rows and not required.issubset(set(rows[0].keys())):
                raise CommandError(f'Formato leaves report non valido: colonne richieste mancanti in {csv_path}')

            for row in rows:
                leave_type = self._norm(row.get('Leave Type'))
                if leave_type != 'Programmazione':
                    continue
                employee = self._fold(self._norm(row.get('Employee')))
                department = self._norm(row.get('Department')).split()[-1].strip().lower() if self._norm(row.get('Department')) else ''
                status = self._norm(row.get('Status'))
                if not employee or not status:
                    continue
                try:
                    start_day = datetime.strptime(self._norm(row.get('From')), '%Y-%m-%d').date()
                    end_day = datetime.strptime(self._norm(row.get('To')), '%Y-%m-%d').date()
                except ValueError:
                    continue
                for legacy_day in self._iter_days(start_day, end_day):
                    status_map[(employee, department, legacy_day)].add(status)
        return status_map

    @staticmethod
    def _department_from_group(raw_group: str) -> str:
        chunks = [part.strip(" ,;:.()[]{}") for part in str(raw_group or '').split()]
        chunks = [part for part in chunks if part]
        return chunks[-1].lower() if chunks else ''

    @staticmethod
    def _resolve_plan_status(legacy_statuses: set[str]) -> str:
        if 'New' in legacy_statuses:
            return MonthlyPlan.Status.SUBMITTED
        if 'Rejected' in legacy_statuses:
            return MonthlyPlan.Status.REJECTED
        return MonthlyPlan.Status.APPROVED

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

        folded_full_name = self._fold(f'{raw_firstname} {raw_lastname}')
        if folded_full_name:
            full_name_matches = [
                user
                for user in users
                if self._fold(f'{user.first_name} {user.last_name}') == folded_full_name
            ]
            if len(full_name_matches) == 1:
                return full_name_matches[0], 'full_name'

        folded_lastname = self._fold(raw_lastname)
        folded_firstname = self._fold(raw_firstname)
        if folded_lastname:
            surname_matches = [
                user for user in users if self._fold(user.last_name) == folded_lastname
            ]
            if len(surname_matches) > 1 and folded_firstname:
                narrowed = [
                    user for user in surname_matches if self._fold(user.first_name) == folded_firstname
                ]
                if len(narrowed) == 1:
                    return narrowed[0], 'lastname_firstname'

        return None, ''

    def handle(self, *args, **options):
        csv_path = Path(options['csv_path']).expanduser()
        dry_run = bool(options.get('dry_run'))
        email_filter = str(options.get('email_filter') or '').strip().lower()
        overwrite_existing = bool(options.get('overwrite_existing'))
        leaves_report_csv_paths = [str(item).strip() for item in (options.get('leaves_report_csv') or []) if str(item).strip()]

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
        if today.month == 12:
            month_after_next_start = date(today.year + 1, 2, 1)
        else:
            if today.month == 11:
                month_after_next_start = date(today.year + 1, 1, 1)
            else:
                month_after_next_start = date(today.year, today.month + 2, 1)
        users = list(
            User.objects.only('id', 'username', 'email', 'first_name', 'last_name', 'department')
        )
        leaves_report_status_map = self._load_leaves_report_status_map(leaves_report_csv_paths)

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
            'days_future_skipped': 0,
            'days_next_month_without_status_skipped': 0,
            'days_next_month_unsupported_status_skipped': 0,
            'rows_no_usable_days': 0,
            'plans_overwritten': 0,
            'plans_status_approved': 0,
            'plans_status_submitted': 0,
            'plans_status_rejected': 0,
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
            folded_full_name = self._fold(f'{raw_firstname} {raw_lastname}')
            folded_department = self._department_from_group(row[0])
            for legacy_day in self._iter_days(start_day, end_day):
                if legacy_day >= month_after_next_start:
                    counters['days_future_skipped'] += 1
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

                legacy_status = ''
                if legacy_day >= current_month_start:
                    statuses = leaves_report_status_map.get((folded_full_name, folded_department, legacy_day), set())
                    if not statuses:
                        counters['days_next_month_without_status_skipped'] += 1
                        continue
                    if 'New' in statuses:
                        legacy_status = 'New'
                    elif 'Rejected' in statuses:
                        legacy_status = 'Rejected'
                    elif 'Approved' in statuses:
                        legacy_status = 'Approved'
                    else:
                        counters['days_next_month_unsupported_status_skipped'] += 1
                        continue

                key = self._plan_key(user_id=user.id, year=legacy_day.year, month=legacy_day.month)
                bucket = grouped.get(key)
                if not bucket:
                    bucket = PlanImportBucket(user=user, year=legacy_day.year, month=legacy_day.month)
                    grouped[key] = bucket
                bucket.days.add(legacy_day)
                if legacy_status:
                    bucket.legacy_statuses.add(legacy_status)
                usable_past_days += 1

            if usable_past_days == 0:
                counters['rows_no_usable_days'] += 1

        existing_plans = {
            self._plan_key(user_id=plan.user_id, year=plan.year, month=plan.month): plan
            for plan in MonthlyPlan.objects.filter(
                user_id__in=[bucket.user.id for bucket in grouped.values()]
            ).only('id', 'user_id', 'year', 'month')
        }

        try:
            with transaction.atomic():
                for key, bucket in sorted(
                    grouped.items(),
                    key=lambda item: (item[1].user.username, item[1].year, item[1].month),
                ):
                    if not bucket.days:
                        continue
                    existing_plan = existing_plans.get(key)
                    if existing_plan and not overwrite_existing:
                        counters['plans_existing_skipped'] += 1
                        continue

                    if dry_run:
                        plan_status = self._resolve_plan_status(bucket.legacy_statuses)
                        if existing_plan:
                            counters['plans_overwritten'] += 1
                        else:
                            counters['plans_created'] += 1
                        counters[f'plans_status_{plan_status.lower()}'] += 1
                        counters['days_imported'] += len(bucket.days)
                        continue

                    now = timezone.now()
                    plan_status = self._resolve_plan_status(bucket.legacy_statuses)
                    if existing_plan:
                        plan = MonthlyPlan.objects.select_for_update().get(pk=existing_plan.id)
                        existing_notes_by_day = {
                            item.day: item.notes or ''
                            for item in plan.days.all().only('day', 'notes')
                        }
                        plan.status = plan_status
                        plan.submitted_at = now
                        plan.approved_at = now if plan_status == MonthlyPlan.Status.APPROVED else None
                        plan.approved_by = None
                        plan.rejection_reason = 'Import legacy CSV: stato rifiutato' if plan_status == MonthlyPlan.Status.REJECTED else ''
                        plan.approved_days_snapshot = [] if plan_status != MonthlyPlan.Status.APPROVED else plan.approved_days_snapshot
                        plan.save(
                            update_fields=[
                                'status',
                                'submitted_at',
                                'approved_at',
                                'approved_by',
                                'rejection_reason',
                                'approved_days_snapshot',
                                'updated_at',
                            ]
                        )
                        plan.days.all().delete()
                    else:
                        plan = MonthlyPlan.objects.create(
                            user=bucket.user,
                            year=bucket.year,
                            month=bucket.month,
                            status=plan_status,
                            submitted_at=now,
                            approved_at=now if plan_status == MonthlyPlan.Status.APPROVED else None,
                            rejection_reason='Import legacy CSV: stato rifiutato' if plan_status == MonthlyPlan.Status.REJECTED else '',
                        )
                        existing_notes_by_day = {}
                    PlanDay.objects.bulk_create(
                        [
                            PlanDay(
                                plan=plan,
                                day=day_value,
                                work_type=PlanDay.WorkType.REMOTE,
                                notes=existing_notes_by_day.get(day_value, ''),
                            )
                            for day_value in sorted(bucket.days)
                        ]
                    )
                    if plan_status == MonthlyPlan.Status.APPROVED:
                        plan.capture_approved_snapshot()
                    else:
                        plan.approved_days_snapshot = []
                        plan.save(update_fields=['approved_days_snapshot', 'updated_at'])
                    AuditLog.track(
                        actor=None,
                        action='legacy_icb_backup_overwritten' if existing_plan else 'legacy_icb_backup_imported',
                        target_type='MonthlyPlan',
                        target_id=plan.id,
                        metadata={
                            'source_file': str(csv_path),
                            'username': bucket.user.username,
                            'email': bucket.user.email or '',
                            'year': bucket.year,
                            'month': bucket.month,
                            'days_imported': len(bucket.days),
                            'legacy_statuses': sorted(bucket.legacy_statuses),
                            'final_status': plan_status,
                        },
                    )
                    if existing_plan:
                        counters['plans_overwritten'] += 1
                    else:
                        counters['plans_created'] += 1
                    counters[f'plans_status_{plan_status.lower()}'] += 1
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
                f'piani sovrascritti={counters["plans_overwritten"]}, '
                f'piani esistenti saltati={counters["plans_existing_skipped"]}, '
                f'giorni importati={counters["days_imported"]}, '
                f'piani_status_approved={counters["plans_status_approved"]}, '
                f'piani_status_submitted={counters["plans_status_submitted"]}, '
                f'piani_status_rejected={counters["plans_status_rejected"]}'
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
            f'future={counters["days_future_skipped"]}, '
            f'corrente_prossimo_senza_status={counters["days_next_month_without_status_skipped"]}, '
            f'corrente_prossimo_status_non_supportato={counters["days_next_month_unsupported_status_skipped"]}, '
            f'righe senza giorni utili={counters["rows_no_usable_days"]}'
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
