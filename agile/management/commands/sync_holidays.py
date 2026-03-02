from django.core.management.base import BaseCommand

from agile.models import Holiday


class Command(BaseCommand):
    help = 'Sincronizza nel DB le festivita nazionali italiane per un anno.'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, required=True, help='Anno da sincronizzare (es. 2026)')
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help='Aggiorna il nome delle festivita gia presenti per lo stesso giorno globale',
        )

    def handle(self, *args, **options):
        year = options['year']
        overwrite = options['overwrite']

        try:
            import holidays as holidays_lib
        except ImportError:
            self.stderr.write(self.style.ERROR('Libreria holidays non installata. Esegui pip install -r requirements.txt'))
            return

        italy_holidays = holidays_lib.country_holidays('IT', years=[year])

        created = 0
        updated = 0
        skipped = 0

        for holiday_day, holiday_name in sorted(italy_holidays.items()):
            obj, is_created = Holiday.objects.get_or_create(
                day=holiday_day,
                department='',
                defaults={'name': str(holiday_name)},
            )
            if is_created:
                created += 1
                continue

            if overwrite:
                obj.name = str(holiday_name)
                obj.save(update_fields=['name'])
                updated += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Sync completata per {year}: create={created}, aggiornate={updated}, saltate={skipped}'
            )
        )
