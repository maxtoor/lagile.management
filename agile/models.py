from datetime import date

from django.contrib.auth.models import AbstractUser, Group
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db import models


def _site_choices() -> tuple[tuple[str, str], ...]:
    sites = getattr(settings, 'AGILE_SITES', ['Napoli', 'Catania', 'Sassari', 'Padova'])
    return tuple((site, site) for site in sites)


SITE_CHOICES = _site_choices()

HOLIDAY_SITE_CHOICES = (('', 'Tutte le sedi'),) + SITE_CHOICES


class User(AbstractUser):
    class Role(models.TextChoices):
        EMPLOYEE = 'EMPLOYEE', 'Dipendente'
        ADMIN = 'ADMIN', 'Referente Amministrativo'
        SUPERADMIN = 'SUPERADMIN', 'Super Admin'

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.EMPLOYEE)
    aila_subscribed = models.BooleanField('Sottoscrizione AILA', default=False)
    onboarding_pending = models.BooleanField('Onboarding in attesa', default=False)
    auto_approve = models.BooleanField('Approvazione automatica', default=False)
    department = models.CharField('Sede', max_length=120, blank=True, choices=SITE_CHOICES)
    manager = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='employees',
        verbose_name='Referente amministrativo',
        limit_choices_to=Q(role__in=['ADMIN', 'SUPERADMIN']) | Q(is_superuser=True),
    )

    @property
    def is_approver(self) -> bool:
        return self.role in {self.Role.ADMIN, self.Role.SUPERADMIN}

    def _align_role_permissions(self):
        # Allineamento automatico ruolo/permesse:
        # - superuser => SUPERADMIN + staff
        # - SUPERADMIN => staff
        # - ADMIN/EMPLOYEE => non staff
        if self.is_superuser:
            self.role = self.Role.SUPERADMIN
            self.is_staff = True
            return

        if self.role == self.Role.SUPERADMIN:
            self.is_staff = True
            return

        self.is_staff = False

    def clean(self):
        self._align_role_permissions()
        super().clean()
        if self.manager_id and self.manager_id == self.id:
            raise ValidationError('Un utente non puo avere se stesso come referente amministrativo')

    def save(self, *args, **kwargs):
        self._align_role_permissions()
        if self.aila_subscribed:
            self.onboarding_pending = False
        super().save(*args, **kwargs)


class AgileGroup(Group):
    class Meta:
        proxy = True
        app_label = 'agile'
        verbose_name = 'Gruppo'
        verbose_name_plural = 'Gruppi'


class MonthlyPlan(models.Model):
    DEFAULT_MAX_REMOTE_DAYS = 10
    DEFAULT_MAX_REMOTE_DAYS_FEBRUARY = 8

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Bozza'
        SUBMITTED = 'SUBMITTED', 'Inviato'
        APPROVED = 'APPROVED', 'Approvato'
        REJECTED = 'REJECTED', 'Rifiutato'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='monthly_plans')
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_plans')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    approved_days_snapshot = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'year', 'month')
        ordering = ('-year', '-month', 'user__username')

    def clean(self) -> None:
        if self.month < 1 or self.month > 12:
            raise ValidationError('Il mese deve essere tra 1 e 12')

    @classmethod
    def max_remote_days_for_month(cls, month: int, policy: 'DepartmentPolicy | None' = None) -> int:
        if policy:
            if month == 2 and policy.february_max_remote_days is not None:
                return policy.february_max_remote_days
            if policy.max_remote_days is not None:
                return policy.max_remote_days
        return cls.DEFAULT_MAX_REMOTE_DAYS_FEBRUARY if month == 2 else cls.DEFAULT_MAX_REMOTE_DAYS

    @staticmethod
    def get_department_policy(department: str) -> 'DepartmentPolicy | None':
        if not department:
            return None
        return DepartmentPolicy.objects.filter(department=department).first()

    @classmethod
    def validate_business_rules(
        cls,
        *,
        month: int,
        remote_days: int,
        on_site_days: int,
        policy: 'DepartmentPolicy | None' = None,
    ) -> None:
        max_remote_days = cls.max_remote_days_for_month(month, policy)
        if remote_days > max_remote_days:
            raise ValidationError(
                f'Giorni di lavoro agile oltre il massimo consentito: {remote_days}/{max_remote_days}'
            )

        require_prevalence = True if not policy else policy.require_on_site_prevalence
        if require_prevalence and remote_days > 0 and on_site_days <= remote_days:
            raise ValidationError(
                'Il lavoro in presenza deve essere prevalente rispetto ai giorni di lavoro agile'
            )

    @staticmethod
    def easter_sunday(*, year: int) -> date:
        # Gregorian computus (Meeus/Jones/Butcher)
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        return date(year, month, day)

    @staticmethod
    def italian_national_holidays_for_month(*, year: int, month: int) -> dict[date, str]:
        easter = MonthlyPlan.easter_sunday(year=year)
        easter_monday = easter.fromordinal(easter.toordinal() + 1)

        try:
            import holidays as holidays_lib
        except ImportError:
            out: dict[date, str] = {}
            if easter.month == month:
                out[easter] = 'Pasqua'
            if easter_monday.month == month:
                out[easter_monday] = "Lunedi dell'Angelo"
            return out

        italian_holidays = holidays_lib.country_holidays('IT', years=[year])
        out = {
            holiday_day: str(holiday_name)
            for holiday_day, holiday_name in italian_holidays.items()
            if holiday_day.month == month
        }
        if easter.month == month and easter not in out:
            out[easter] = 'Pasqua'
        if easter_monday.month == month and easter_monday not in out:
            out[easter_monday] = "Lunedi dell'Angelo"
        return out

    @staticmethod
    def italian_national_holiday_days_for_month(*, year: int, month: int) -> set[date]:
        return set(MonthlyPlan.italian_national_holidays_for_month(year=year, month=month).keys())

    @staticmethod
    def holiday_labels_for_month(*, year: int, month: int, department: str) -> dict[date, str]:
        labels: dict[date, str] = dict(MonthlyPlan.italian_national_holidays_for_month(year=year, month=month))
        query = Holiday.objects.filter(day__year=year, day__month=month)
        if department:
            query = query.filter(Q(department='') | Q(department=department))
        else:
            query = query.filter(department='')
        for holiday_day, holiday_name in query.values_list('day', 'name'):
            name = (holiday_name or '').strip() or 'Festivita'
            if holiday_day in labels:
                current = labels[holiday_day]
                if name not in current:
                    labels[holiday_day] = f'{current} / {name}'
            else:
                labels[holiday_day] = name
        return labels

    @staticmethod
    def holiday_days_for_month(*, year: int, month: int, department: str) -> set[date]:
        return set(MonthlyPlan.holiday_labels_for_month(year=year, month=month, department=department).keys())

    @classmethod
    def validate_day_payloads(
        cls,
        *,
        year: int,
        month: int,
        department: str,
        day_payloads: list[dict],
    ) -> None:
        seen_days: set[date] = set()
        holidays = cls.holiday_days_for_month(year=year, month=month, department=department)
        remote_days = 0
        on_site_days = 0

        for payload in day_payloads:
            day = payload['day']
            work_type = payload['work_type']

            if day.year != year or day.month != month:
                raise ValidationError('Ogni giorno deve appartenere allo stesso mese del piano')
            if day in seen_days:
                raise ValidationError(f'Giorno duplicato nel piano: {day.isoformat()}')
            seen_days.add(day)

            if day.weekday() >= 5:
                raise ValidationError(f'Weekend non consentito nel piano: {day.isoformat()}')
            if day in holidays:
                raise ValidationError(f'Festivita non consentita nel piano: {day.isoformat()}')

            if work_type == PlanDay.WorkType.REMOTE:
                remote_days += 1
            elif work_type == PlanDay.WorkType.ON_SITE:
                on_site_days += 1

        policy = cls.get_department_policy(department)
        cls.validate_business_rules(
            month=month,
            remote_days=remote_days,
            on_site_days=on_site_days,
            policy=policy,
        )

    def validate_existing_days(self) -> None:
        day_payloads = list(self.days.values('day', 'work_type'))
        self.validate_day_payloads(
            year=self.year,
            month=self.month,
            department=self.user.department,
            day_payloads=day_payloads,
        )

    def capture_approved_snapshot(self) -> None:
        payload = [
            {
                'day': item.day.isoformat(),
                'work_type': item.work_type,
                'notes': item.notes or '',
            }
            for item in self.days.all().order_by('day')
        ]
        self.approved_days_snapshot = payload
        self.save(update_fields=['approved_days_snapshot', 'updated_at'])

    def restore_from_approved_snapshot(self) -> None:
        payload = self.approved_days_snapshot or []
        if not payload:
            raise ValidationError('Nessuno snapshot approvato disponibile')

        parsed = []
        for item in payload:
            day_raw = item.get('day')
            work_type = item.get('work_type')
            notes = item.get('notes', '') or ''
            if not day_raw or work_type not in {PlanDay.WorkType.ON_SITE, PlanDay.WorkType.REMOTE}:
                raise ValidationError('Snapshot approvato non valido')
            parsed.append(
                {
                    'day': date.fromisoformat(str(day_raw)),
                    'work_type': work_type,
                    'notes': notes if work_type == PlanDay.WorkType.REMOTE else '',
                }
            )

        self.validate_day_payloads(
            year=self.year,
            month=self.month,
            department=self.user.department,
            day_payloads=parsed,
        )

        self.days.all().delete()
        for entry in parsed:
            PlanDay.objects.create(
                plan=self,
                day=entry['day'],
                work_type=entry['work_type'],
                notes=entry['notes'],
            )

    def __str__(self) -> str:
        return f'{self.user.username} - {self.month:02d}/{self.year}'


class PlanDay(models.Model):
    class WorkType(models.TextChoices):
        ON_SITE = 'ON_SITE', 'In sede'
        REMOTE = 'REMOTE', 'Lavoro agile'

    plan = models.ForeignKey(MonthlyPlan, on_delete=models.CASCADE, related_name='days')
    day = models.DateField()
    work_type = models.CharField(max_length=20, choices=WorkType.choices)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('plan', 'day')
        ordering = ('day',)

    def clean(self) -> None:
        if self.day.year != self.plan.year or self.day.month != self.plan.month:
            raise ValidationError('Il giorno deve appartenere allo stesso mese del piano')


class DepartmentPolicy(models.Model):
    department = models.CharField('Sede', max_length=120, unique=True, choices=SITE_CHOICES)
    max_remote_days = models.PositiveSmallIntegerField(null=True, blank=True)
    february_max_remote_days = models.PositiveSmallIntegerField(null=True, blank=True)
    require_on_site_prevalence = models.BooleanField(default=True)

    class Meta:
        ordering = ('department',)

    def __str__(self) -> str:
        return self.department


class Holiday(models.Model):
    day = models.DateField()
    name = models.CharField(max_length=120)
    department = models.CharField(
        'Sede',
        max_length=120,
        blank=True,
        choices=HOLIDAY_SITE_CHOICES,
        help_text='Vuoto = festivita valida per tutte le sedi',
    )

    class Meta:
        unique_together = ('day', 'department')
        ordering = ('day', 'department')

    def __str__(self) -> str:
        return f'{self.day.isoformat()} - {self.name}'


class ChangeRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'In attesa'
        APPROVED = 'APPROVED', 'Approvata'
        REJECTED = 'REJECTED', 'Rifiutata'

    plan = models.ForeignKey(MonthlyPlan, on_delete=models.CASCADE, related_name='change_requests')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='change_requests')
    reason = models.TextField()
    response_reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    processed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='processed_change_requests',
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)


class SystemEmailTemplate(models.Model):
    class Key(models.TextChoices):
        CHANGE_REQUEST_SUBMITTED = 'CHANGE_REQUEST_SUBMITTED', 'Richiesta variazione inviata'
        REMINDER_PENDING_SUBMISSION = 'REMINDER_PENDING_SUBMISSION', 'Promemoria invio piano'
        MANAGER_MONTHLY_SUMMARY = 'MANAGER_MONTHLY_SUMMARY', 'Riepilogo mensile referente'
        PLAN_APPROVED = 'PLAN_APPROVED', 'Piano approvato'
        PLAN_REJECTED = 'PLAN_REJECTED', 'Piano rifiutato'
        CHANGE_APPROVED = 'CHANGE_APPROVED', 'Variazione approvata'
        CHANGE_REJECTED = 'CHANGE_REJECTED', 'Variazione rifiutata'

    key = models.CharField(max_length=40, unique=True, choices=Key.choices)
    subject_template = models.CharField(max_length=255)
    body_template = models.TextField(
        help_text=(
            'Template con segnaposto Python-style, es: {first_name}, {username}, {month_label}, '
            '{status_label}, {rejection_reason}, {change_reason}'
        )
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('key',)
        verbose_name = 'Template email di sistema'
        verbose_name_plural = 'Template email di sistema'

    def __str__(self) -> str:
        return self.get_key_display()


class AppSetting(models.Model):
    class DateFormat(models.TextChoices):
        IT = 'IT', 'Italiano (gg/mm/aaaa)'
        ISO = 'ISO', 'ISO (aaaa-mm-gg)'

    date_display_format = models.CharField(
        max_length=8,
        choices=DateFormat.choices,
        blank=True,
        help_text='Se vuoto usa AGILE_DATE_DISPLAY_FORMAT da .env',
    )
    login_logo_url = models.URLField(
        blank=True,
        help_text='Se vuoto usa AGILE_LOGIN_LOGO_URL da .env',
    )
    company_name = models.CharField(
        max_length=120,
        blank=True,
        help_text='Se vuoto usa AGILE_COMPANY_NAME da .env',
    )
    copyright_year = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Se vuoto usa AGILE_COPYRIGHT_YEAR da .env',
    )
    default_from_email = models.EmailField(
        blank=True,
        help_text='Se vuoto usa DEFAULT_FROM_EMAIL da .env',
    )
    email_from_name = models.CharField(
        max_length=120,
        blank=True,
        help_text='Se vuoto usa AGILE_EMAIL_FROM_NAME da .env',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Impostazioni applicazione'
        verbose_name_plural = 'Impostazioni applicazione'

    def __str__(self) -> str:
        return 'Impostazioni applicazione'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from .runtime_settings import clear_runtime_settings_cache

        clear_runtime_settings_cache()

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        from .runtime_settings import clear_runtime_settings_cache

        clear_runtime_settings_cache()
        return result


class AuditLog(models.Model):
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=60)
    target_type = models.CharField(max_length=60)
    target_id = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('-created_at',)

    @classmethod
    def track(cls, *, actor: User | None, action: str, target_type: str, target_id: int | None, metadata: dict | None = None) -> 'AuditLog':
        return cls.objects.create(
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata=metadata or {},
        )
