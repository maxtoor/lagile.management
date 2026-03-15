import calendar
from datetime import date, timedelta
from email.utils import formataddr

from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone

from agile.models import AuditLog, MonthlyPlan, SystemEmailTemplate, User
from agile.runtime_settings import build_email_link_context, get_runtime_setting


class _SafeDict(dict):
    def __missing__(self, key):
        return '{' + str(key) + '}'


class Command(BaseCommand):
    help = (
        "Invia promemoria agli utenti attivi senza auto-approvazione che non hanno ancora "
        "inviato/approvato il piano del mese successivo, a partire da N giorni prima "
        "della fine del mese corrente e al massimo una volta al giorno."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Esegue anche se oggi non coincide con la data configurata',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula invio senza inviare email reali',
        )
        parser.add_argument(
            '--date',
            dest='as_of_date',
            help='Data di riferimento YYYY-MM-DD (default: data server locale)',
        )

    @staticmethod
    def _sender_from_env() -> str | None:
        from_email = (get_runtime_setting('DEFAULT_FROM_EMAIL', '') or '').strip()
        from_name = (get_runtime_setting('AGILE_EMAIL_FROM_NAME', '') or '').strip()
        if not from_email:
            return None
        if not from_name:
            return from_email
        return formataddr((from_name, from_email))

    @staticmethod
    def _next_year_month(today: date) -> tuple[int, int]:
        if today.month == 12:
            return today.year + 1, 1
        return today.year, today.month + 1

    @staticmethod
    def _scheduled_run_window(today: date, days_before_month_end: int) -> tuple[date, date]:
        _, last_day = calendar.monthrange(today.year, today.month)
        end_date = date(today.year, today.month, last_day)
        safe_days = max(0, int(days_before_month_end))
        start_date = end_date - timedelta(days=safe_days)
        return start_date, end_date

    @staticmethod
    def _month_name_year_it(year: int, month: int) -> str:
        month_names = [
            'gennaio',
            'febbraio',
            'marzo',
            'aprile',
            'maggio',
            'giugno',
            'luglio',
            'agosto',
            'settembre',
            'ottobre',
            'novembre',
            'dicembre',
        ]
        idx = month - 1
        if 0 <= idx < len(month_names):
            return f'{month_names[idx]} {year}'
        return f'{month:02d}/{year}'

    @staticmethod
    def _render_from_template(*, key: str, default_subject: str, default_body: str, context: dict) -> tuple[str, str]:
        tpl = SystemEmailTemplate.objects.filter(key=key).only('subject_template', 'body_template').first()
        subject_t = (tpl.subject_template if tpl and tpl.subject_template else default_subject) or default_subject
        body_t = (tpl.body_template if tpl and tpl.body_template else default_body) or default_body
        safe_context = _SafeDict(context or {})
        try:
            subject = subject_t.format_map(safe_context)
        except Exception:
            subject = default_subject.format_map(safe_context)
        try:
            body = body_t.format_map(safe_context)
        except Exception:
            body = default_body.format_map(safe_context)
        return subject, body

    def handle(self, *args, **options):
        as_of_date = (options.get('as_of_date') or '').strip()
        if as_of_date:
            try:
                today = date.fromisoformat(as_of_date)
            except ValueError:
                self.stderr.write(self.style.ERROR('Formato data non valido, usare YYYY-MM-DD'))
                return
        else:
            today = timezone.localdate()

        force = bool(options.get('force'))
        dry_run = bool(options.get('dry_run'))
        days_before_month_end = int(get_runtime_setting('SUBMISSION_REMINDER_OFFSET_DAYS', 0) or 0)
        target_year, target_month = self._next_year_month(today)
        start_date, end_date = self._scheduled_run_window(today, days_before_month_end)

        if not force and not (start_date <= today <= end_date):
            self.stdout.write(
                self.style.WARNING(
                    "Oggi "
                    f"{today.isoformat()} non rientra nella finestra configurata "
                    f"({start_date.isoformat()} - {end_date.isoformat()}), nessuna email inviata"
                )
            )
            return

        month_label = f'{target_month:02d}/{target_year}'
        month_name_year = self._month_name_year_it(target_year, target_month)

        eligible_users = User.objects.filter(
            is_active=True,
            auto_approve=False,
            aila_subscribed=True,
        ).exclude(email__isnull=True).exclude(email__exact='')

        plans = MonthlyPlan.objects.filter(
            user__in=eligible_users,
            year=target_year,
            month=target_month,
        ).values('user_id', 'status')
        plan_status_by_user = {row['user_id']: row['status'] for row in plans}

        sent = 0
        skipped = 0
        errors = 0

        for user in eligible_users:
            status = plan_status_by_user.get(user.id)
            if status in {MonthlyPlan.Status.SUBMITTED, MonthlyPlan.Status.APPROVED}:
                skipped += 1
                continue

            already_sent = AuditLog.objects.filter(
                actor=None,
                action='submission_reminder_sent',
                target_type='User',
                target_id=user.id,
                metadata__year=target_year,
                metadata__month=target_month,
                metadata__sent_on=today.isoformat(),
            ).exists()
            if already_sent:
                skipped += 1
                self.stdout.write(f'Promemoria gia inviato oggi a {user.email} per {month_label}, salto')
                continue

            full_name = f'{(user.first_name or "").strip()} {(user.last_name or "").strip()}'.strip() or user.username
            default_subject = f'Promemoria invio piano lavoro agile - {month_name_year}'
            links = build_email_link_context()
            portal_line = f"Link portale: {links['portal_url']}\n\n" if links['portal_url'] else ''
            default_body = (
                'Gentile {full_name},\n\n'
                'ti ricordiamo di inviare in approvazione il piano di lavoro agile per {month_name_year}.\n'
                'Stato attuale: {plan_status_label}.\n\n'
                '{portal_line}'
                'Puoi accedere al portale per completare l\'invio.'
            )
            subject, body = self._render_from_template(
                key=SystemEmailTemplate.Key.REMINDER_PENDING_SUBMISSION,
                default_subject=default_subject,
                default_body=default_body,
                context={
                    'full_name': full_name,
                    'first_name': (user.first_name or '').strip(),
                    'last_name': (user.last_name or '').strip(),
                    'username': user.username,
                    'month_label': month_label,
                    'month_name_year': month_name_year,
                    'plan_status': status or 'ASSENTE',
                    'plan_status_label': status or 'ASSENTE',
                    'portal_line': portal_line,
                    **links,
                },
            )

            if dry_run:
                self.stdout.write(f'[DRY-RUN] -> {user.email} | {subject}')
                sent += 1
                continue

            try:
                send_mail(
                    subject=subject,
                    message=body,
                    from_email=self._sender_from_env(),
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                AuditLog.track(
                    actor=None,
                    action='submission_reminder_sent',
                    target_type='User',
                    target_id=user.id,
                    metadata={
                        'year': target_year,
                        'month': target_month,
                        'email': user.email,
                        'sent_on': today.isoformat(),
                    },
                )
                sent += 1
                self.stdout.write(self.style.SUCCESS(f'Email inviata a {user.email}'))
            except Exception as exc:
                errors += 1
                self.stderr.write(self.style.ERROR(f'Errore invio a {user.email}: {exc}'))

        suffix = ' (dry-run)' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(
                f'Promemoria completato: inviati={sent}, saltati={skipped}, errori={errors}{suffix}'
            )
        )
