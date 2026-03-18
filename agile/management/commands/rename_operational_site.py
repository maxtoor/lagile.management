from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from agile.models import DepartmentPolicy, Holiday, User


class Command(BaseCommand):
    help = (
        'Rinomina una sede operativa gia esistente nei dati applicativi '
        '(utenti, festivita e policy di sede).'
    )

    def add_arguments(self, parser):
        parser.add_argument('old_name', help='Nome sede operativa attuale')
        parser.add_argument('new_name', help='Nuovo nome sede operativa')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra cosa verrebbe rinominato senza modificare il database',
        )

    def handle(self, *args, **options):
        old_name = str(options['old_name'] or '').strip()
        new_name = str(options['new_name'] or '').strip()
        dry_run = bool(options.get('dry_run'))

        if not old_name or not new_name:
            self.stderr.write(self.style.ERROR('Specificare sia il nome sede attuale sia il nuovo nome'))
            return

        if old_name == new_name:
            self.stderr.write(self.style.ERROR('Il nuovo nome coincide con quello attuale'))
            return

        configured_sites = list(getattr(settings, 'AGILE_SITES', []) or [])
        if new_name not in configured_sites:
            self.stderr.write(
                self.style.ERROR(
                    f"La nuova sede '{new_name}' non e presente in AGILE_SITES. "
                    'Aggiorna prima la configurazione dell\'ambiente.'
                )
            )
            return

        users_qs = User.objects.filter(department=old_name)
        policy_qs = DepartmentPolicy.objects.filter(department=old_name)
        holidays_qs = Holiday.objects.filter(department=old_name)

        user_count = users_qs.count()
        policy_count = policy_qs.count()
        holiday_count = holidays_qs.count()

        target_policy_exists = DepartmentPolicy.objects.filter(department=new_name).exists()
        holiday_conflicts = Holiday.objects.filter(
            department=new_name,
            day__in=holidays_qs.values_list('day', flat=True),
        ).count()

        if target_policy_exists and policy_count:
            self.stderr.write(
                self.style.ERROR(
                    f"Esiste gia una DepartmentPolicy per '{new_name}': impossibile rinominare in sicurezza."
                )
            )
            return

        if holiday_conflicts:
            self.stderr.write(
                self.style.ERROR(
                    f"Trovate {holiday_conflicts} festivita gia presenti su '{new_name}' con le stesse date: "
                    'rinomina interrotta per evitare conflitti.'
                )
            )
            return

        if not user_count and not policy_count and not holiday_count:
            self.stdout.write(
                self.style.WARNING(
                    f"Nessun record da rinominare: la sede '{old_name}' non compare nei dati applicativi."
                )
            )
            return

        summary = (
            f"Rinomina sede operativa '{old_name}' -> '{new_name}': "
            f"utenti={user_count}, policy={policy_count}, festivita={holiday_count}"
        )
        if dry_run:
            self.stdout.write(self.style.WARNING(f'[DRY-RUN] {summary}'))
            return

        with transaction.atomic():
            updated_users = users_qs.update(department=new_name)
            updated_policies = policy_qs.update(department=new_name)
            updated_holidays = holidays_qs.update(department=new_name)

        self.stdout.write(
            self.style.SUCCESS(
                f"{summary}. Aggiornati: utenti={updated_users}, policy={updated_policies}, festivita={updated_holidays}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                'Nota: il comando non modifica AGILE_SITES ne le regole hardcoded degli import CSV. '
                'Se il rename e definitivo, aggiorna anche la configurazione e i mapping di import.'
            )
        )
