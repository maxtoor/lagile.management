from calendar import monthrange
from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from agile.models import AuditLog, MonthlyPlan, PlanDay


class Command(BaseCommand):
    help = (
        'Approva per silenzio assenso i piani ancora in attesa di approvazione '
        'quando il relativo mese e ormai concluso.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula senza modificare i piani',
        )
        parser.add_argument(
            '--date',
            dest='as_of_date',
            help='Data di riferimento YYYY-MM-DD (default: data server locale)',
        )

    @staticmethod
    def _parse_date(value: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise DjangoValidationError('Formato data non valido, usare YYYY-MM-DD') from exc

    @staticmethod
    def _month_start(day: date) -> date:
        return date(day.year, day.month, 1)

    @staticmethod
    def _plan_month_start(plan: MonthlyPlan) -> date:
        return date(plan.year, plan.month, 1)

    @staticmethod
    def _completed_working_day_payloads(plan: MonthlyPlan):
        holidays = MonthlyPlan.holiday_days_for_month(
            year=plan.year,
            month=plan.month,
            department=plan.user.department,
        )
        existing_by_day = {
            item.day: {
                'day': item.day,
                'work_type': item.work_type,
                'notes': item.notes or '',
            }
            for item in plan.days.all()
        }

        payloads = []
        for day_number in range(1, monthrange(plan.year, plan.month)[1] + 1):
            day_value = date(plan.year, plan.month, day_number)
            if day_value.weekday() >= 5 or day_value in holidays:
                continue
            payloads.append(
                existing_by_day.get(
                    day_value,
                    {
                        'day': day_value,
                        'work_type': PlanDay.WorkType.ON_SITE,
                        'notes': '',
                    },
                )
            )
        return payloads

    @staticmethod
    def _materialize_missing_on_site_days(plan: MonthlyPlan, day_payloads) -> None:
        existing_days = {item.day for item in plan.days.all()}
        missing_days = [
            PlanDay(
                plan=plan,
                day=payload['day'],
                work_type=PlanDay.WorkType.ON_SITE,
                notes='',
            )
            for payload in day_payloads
            if payload['day'] not in existing_days and payload['work_type'] == PlanDay.WorkType.ON_SITE
        ]
        if missing_days:
            PlanDay.objects.bulk_create(missing_days)
            if hasattr(plan, '_prefetched_objects_cache'):
                plan._prefetched_objects_cache.pop('days', None)

    def handle(self, *args, **options):
        raw_date = (options.get('as_of_date') or '').strip()
        dry_run = bool(options.get('dry_run'))
        if raw_date:
            try:
                today = self._parse_date(raw_date)
            except DjangoValidationError as exc:
                self.stderr.write(self.style.ERROR(exc.messages[0]))
                return
        else:
            today = timezone.localdate()

        current_month_start = self._month_start(today)
        queryset = (
            MonthlyPlan.objects.filter(status=MonthlyPlan.Status.SUBMITTED)
            .select_related('user')
            .prefetch_related('days')
            .order_by('year', 'month', 'user__username')
        )

        approved = 0
        skipped_current_or_future = 0
        errors = 0

        for plan in queryset:
            if self._plan_month_start(plan) >= current_month_start:
                skipped_current_or_future += 1
                continue

            plan_label = f'{plan.user.username} {plan.month:02d}/{plan.year}'

            try:
                day_payloads = self._completed_working_day_payloads(plan)
                MonthlyPlan.validate_day_payloads(
                    year=plan.year,
                    month=plan.month,
                    department=plan.user.department,
                    day_payloads=day_payloads,
                )
                if dry_run:
                    approved += 1
                    self.stdout.write(f'[DRY-RUN] Approvazione per silenzio assenso: {plan_label}')
                    continue

                with transaction.atomic():
                    self._materialize_missing_on_site_days(plan, day_payloads)
                    now = timezone.now()
                    plan.status = MonthlyPlan.Status.APPROVED
                    plan.approved_by = None
                    plan.approved_at = now
                    plan.rejection_reason = ''
                    plan.save(
                        update_fields=[
                            'status',
                            'approved_by',
                            'approved_at',
                            'rejection_reason',
                            'updated_at',
                        ]
                    )
                    plan.capture_approved_snapshot()
                    AuditLog.track(
                        actor=None,
                        action='plan_silence_approved',
                        target_type='MonthlyPlan',
                        target_id=plan.id,
                        metadata={
                            'year': plan.year,
                            'month': plan.month,
                            'user_id': plan.user_id,
                            'approved_on': today.isoformat(),
                            'reason': 'silenzio_assenso_fine_mese',
                        },
                    )
                approved += 1
                self.stdout.write(self.style.SUCCESS(f'Approvato per silenzio assenso: {plan_label}'))
            except DjangoValidationError as exc:
                errors += 1
                self.stderr.write(self.style.ERROR(f'Errore validazione {plan_label}: {exc.messages}'))
            except Exception as exc:
                errors += 1
                self.stderr.write(self.style.ERROR(f'Errore approvazione {plan_label}: {exc}'))

        suffix = ' (dry-run)' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                'Approvazione silenzio assenso completata: '
                f'approvati={approved}, '
                f'saltati_corrente_o_futuri={skipped_current_or_future}, '
                f'errori={errors}{suffix}'
            )
        )
