from io import StringIO

from django.core.management import BaseCommand, call_command, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = (
        'Procedura unica di import legacy ICB: aggiorna/crea utenti dal CSV completo '
        'e poi importa lo storico Programmazione dei mesi passati.'
    )

    def add_arguments(self, parser):
        parser.add_argument('csv_path', help='Percorso del backup CSV completo ICB')
        parser.add_argument(
            '--with-ldap-sync',
            action='store_true',
            help='Dopo il sync utenti ICB esegue anche l’allineamento anagrafico da LDAP',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula l’intera procedura dentro una transazione unica e poi fa rollback',
        )
        parser.add_argument(
            '--skip-user-sync',
            action='store_true',
            help='Salta la fase anagrafica utenti/referenti dal CSV ICB',
        )
        parser.add_argument(
            '--skip-history-import',
            action='store_true',
            help='Salta la fase di import storico Programmazione',
        )

    @staticmethod
    def _emit_summary(*, label: str, raw_output: str, writer) -> None:
        lines = [line.strip() for line in raw_output.splitlines() if line.strip()]
        if not lines:
            return
        writer.write(f'{label}\n')
        for line in lines:
            if line.startswith('Aggiornamento sedi da CSV completato:'):
                writer.write(f'- {line}\n')
            elif line.startswith('UTENTI_AGGIORNATI:'):
                writer.write(f'- {line}\n')
            elif line.startswith('UTENTI_CREATI:'):
                writer.write(f'- {line}\n')
            elif line.startswith('UTENTI_NON_TROVATI:'):
                writer.write(f'- {line}\n')
            elif line.startswith('Import storico ICB completato'):
                writer.write(f'- {line}\n')
            elif line.startswith('Dettaglio skip:'):
                writer.write(f'- {line}\n')
            elif line.startswith('Match utenti:'):
                writer.write(f'- {line}\n')

    def handle(self, *args, **options):
        csv_path = options['csv_path']
        with_ldap_sync = bool(options.get('with_ldap_sync'))
        dry_run = bool(options.get('dry_run'))
        skip_user_sync = bool(options.get('skip_user_sync'))
        skip_history_import = bool(options.get('skip_history_import'))

        if skip_user_sync and skip_history_import:
            raise CommandError('Nessuna fase da eseguire: hai saltato sia sync utenti sia import storico')

        self.stdout.write(self.style.SUCCESS('Avvio procedura import legacy ICB'))
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    'Modalita dry-run bundle: le due fasi vengono eseguite in una singola transazione e poi annullate'
                )
            )

        try:
            with transaction.atomic():
                if not skip_user_sync:
                    self.stdout.write('')
                    self.stdout.write(self.style.SUCCESS('== Fase 1: sync utenti legacy ICB =='))
                    phase_stdout = StringIO()
                    call_command(
                        'update_user_sites_from_csv_icb',
                        csv_path,
                        email_column='Email',
                        site_column='Gruppo',
                        site_mode='last-word',
                        fallback_lastname=True,
                        lastname_column='Cognome',
                        firstname_column='Nome',
                        enrich_managers_from_csv=True,
                        with_ldap_sync=with_ldap_sync,
                        dry_run=False,
                        stdout=phase_stdout,
                        stderr=self.stderr,
                    )
                    self._emit_summary(
                        label='Riepilogo fase 1:',
                        raw_output=phase_stdout.getvalue(),
                        writer=self.stdout,
                    )

                if not skip_history_import:
                    self.stdout.write('')
                    self.stdout.write(self.style.SUCCESS('== Fase 2: import storico Programmazione =='))
                    phase_stdout = StringIO()
                    call_command(
                        'import_legacy_icb_backup',
                        csv_path,
                        dry_run=False,
                        stdout=phase_stdout,
                        stderr=self.stderr,
                    )
                    self._emit_summary(
                        label='Riepilogo fase 2:',
                        raw_output=phase_stdout.getvalue(),
                        writer=self.stdout,
                    )

                if dry_run:
                    transaction.set_rollback(True)
        except Exception as exc:
            raise CommandError(f'Procedura import legacy ICB fallita: {exc}') from exc

        suffix = ' (dry-run completato, nessuna modifica salvata)' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(f'Procedura import legacy ICB completata{suffix}'))
