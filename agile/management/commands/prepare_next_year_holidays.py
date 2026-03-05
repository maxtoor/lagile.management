from datetime import date
from email.utils import formataddr

from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from agile.models import AuditLog, Holiday, MonthlyPlan, User
from agile.runtime_settings import get_runtime_setting


class Command(BaseCommand):
    help = (
        "Il 1 dicembre prepara le festivita dell'anno successivo: "
        "sincronizza festivita nazionali e copia le festivita per sede dall'anno corrente."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Esegue anche se oggi non e il 1 dicembre',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula senza salvare modifiche e senza inviare email',
        )
        parser.add_argument(
            '--date',
            dest='as_of_date',
            help='Data di riferimento YYYY-MM-DD (default: data server locale)',
        )
        parser.add_argument(
            '--year',
            type=int,
            help="Anno target da preparare (default: anno successivo alla data corrente)",
        )

    @staticmethod
    def _sender_from_runtime() -> str | None:
        from_email = (get_runtime_setting('DEFAULT_FROM_EMAIL', '') or '').strip()
        from_name = (get_runtime_setting('AGILE_EMAIL_FROM_NAME', '') or '').strip()
        if not from_email:
            return None
        if not from_name:
            return from_email
        return formataddr((from_name, from_email))

    @staticmethod
    def _italian_national_holidays(year: int) -> dict[date, str]:
        labels: dict[date, str] = {}
        try:
            import holidays as holidays_lib

            labels = {
                d: str(name)
                for d, name in holidays_lib.country_holidays('IT', years=[year]).items()
            }
        except ImportError:
            labels = {}

        easter = MonthlyPlan.easter_sunday(year=year)
        easter_monday = easter.fromordinal(easter.toordinal() + 1)
        labels.setdefault(easter, 'Pasqua')
        labels.setdefault(easter_monday, "Lunedi dell'Angelo")
        return labels

    @staticmethod
    def _target_year(today: date, explicit_year: int | None) -> int:
        if explicit_year:
            return explicit_year
        return today.year + 1

    @staticmethod
    def _notify_superusers(*, target_year: int, source_year: int, summary_lines: list[str], dry_run: bool) -> None:
        if dry_run:
            return
        recipients = list(
            User.objects.filter(is_superuser=True, is_active=True)
            .exclude(email__isnull=True)
            .exclude(email__exact='')
            .values_list('email', flat=True)
        )
        if not recipients:
            return
        subject = f'Aggiornamento festivita {target_year} completato'
        body = (
            f"Aggiornamento automatico festivita completato per l'anno {target_year}.\n"
            f"Anno sorgente festivita per sede: {source_year}.\n\n"
            + '\n'.join(summary_lines)
        )
        send_mail(
            subject=subject,
            message=body,
            from_email=Command._sender_from_runtime(),
            recipient_list=recipients,
            fail_silently=False,
        )

    def handle(self, *args, **options):
        as_of_date = (options.get('as_of_date') or '').strip()
        force = bool(options.get('force'))
        dry_run = bool(options.get('dry_run'))
        explicit_year = options.get('year')

        if as_of_date:
            try:
                today = date.fromisoformat(as_of_date)
            except ValueError:
                self.stderr.write(self.style.ERROR('Formato data non valido, usare YYYY-MM-DD'))
                return
        else:
            today = timezone.localdate()

        if explicit_year and explicit_year < 2000:
            self.stderr.write(self.style.ERROR('Anno target non valido'))
            return

        if not force and explicit_year is None and not (today.month == 12 and today.day == 1):
            self.stdout.write(
                self.style.WARNING(
                    f'Oggi {today.isoformat()} non e il 1 dicembre, nessun aggiornamento festivita eseguito'
                )
            )
            return

        target_year = self._target_year(today, explicit_year)
        source_year = target_year - 1

        if not dry_run:
            already_done = AuditLog.objects.filter(
                actor=None,
                action='yearly_holiday_rollover_completed',
                metadata__target_year=target_year,
            ).exists()
            if already_done and not force:
                self.stdout.write(
                    self.style.WARNING(
                        f'Aggiornamento festivita per {target_year} gia eseguito in precedenza, nessuna azione'
                    )
                )
                return

        national_created = 0
        national_updated = 0
        national_unchanged = 0
        site_created = 0
        site_updated = 0
        site_unchanged = 0
        site_skipped_invalid_date = 0

        with transaction.atomic():
            national_labels = self._italian_national_holidays(target_year)
            for holiday_day, holiday_name in sorted(national_labels.items()):
                obj, created = Holiday.objects.get_or_create(
                    day=holiday_day,
                    department='',
                    defaults={'name': holiday_name},
                )
                if created:
                    national_created += 1
                    continue
                if obj.name != holiday_name:
                    obj.name = holiday_name
                    if not dry_run:
                        obj.save(update_fields=['name'])
                    national_updated += 1
                else:
                    national_unchanged += 1

            source_site_holidays = Holiday.objects.filter(day__year=source_year).exclude(department='')
            for src in source_site_holidays:
                try:
                    target_day = src.day.replace(year=target_year)
                except ValueError:
                    site_skipped_invalid_date += 1
                    continue

                obj, created = Holiday.objects.get_or_create(
                    day=target_day,
                    department=src.department,
                    defaults={'name': src.name},
                )
                if created:
                    site_created += 1
                    continue
                if obj.name != src.name:
                    obj.name = src.name
                    if not dry_run:
                        obj.save(update_fields=['name'])
                    site_updated += 1
                else:
                    site_unchanged += 1

            if dry_run:
                transaction.set_rollback(True)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[DRY-RUN] Aggiornamento festivita simulato per {target_year}, nessuna modifica salvata'
                )
            )

        summary_lines = [
            f'- Nazionali: create={national_created}, aggiornate={national_updated}, invarianti={national_unchanged}',
            f'- Per sede (copiate da {source_year}): create={site_created}, aggiornate={site_updated}, invarianti={site_unchanged}, date_non_valide={site_skipped_invalid_date}',
        ]
        self.stdout.write(self.style.SUCCESS('\n'.join(summary_lines)))

        if not dry_run:
            AuditLog.track(
                actor=None,
                action='yearly_holiday_rollover_completed',
                target_type='Holiday',
                target_id=None,
                metadata={
                    'executed_on': today.isoformat(),
                    'target_year': target_year,
                    'source_year': source_year,
                    'national_created': national_created,
                    'national_updated': national_updated,
                    'national_unchanged': national_unchanged,
                    'site_created': site_created,
                    'site_updated': site_updated,
                    'site_unchanged': site_unchanged,
                    'site_skipped_invalid_date': site_skipped_invalid_date,
                },
            )
            try:
                self._notify_superusers(
                    target_year=target_year,
                    source_year=source_year,
                    summary_lines=summary_lines,
                    dry_run=dry_run,
                )
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f'Invio email superuser fallito: {exc}'))
