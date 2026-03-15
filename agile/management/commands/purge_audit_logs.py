from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from agile.models import AuditLog


class Command(BaseCommand):
    help = 'Elimina gli audit log piu vecchi di una certa soglia temporale.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=90,
            help='Mantiene gli ultimi N giorni di audit log (default: 90)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra quanti record verrebbero eliminati senza modificare il database',
        )

    def handle(self, *args, **options):
        days = int(options.get('days') or 90)
        dry_run = bool(options.get('dry_run'))

        if days < 1:
            self.stderr.write(self.style.ERROR('Il numero di giorni deve essere >= 1'))
            return

        cutoff = timezone.now() - timedelta(days=days)
        queryset = AuditLog.objects.filter(created_at__lt=cutoff)
        total = queryset.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[DRY-RUN] Audit log da eliminare: {total} (created_at < {cutoff.isoformat()})'
                )
            )
            return

        with transaction.atomic():
            deleted, _ = queryset.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f'Audit log eliminati: {deleted} (created_at < {cutoff.isoformat()})'
            )
        )
