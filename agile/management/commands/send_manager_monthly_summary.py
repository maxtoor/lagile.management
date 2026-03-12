from __future__ import annotations

import calendar
from datetime import date
from email.utils import formataddr
from typing import Optional

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
        'Primo giorno del mese: invia ai referenti un riepilogo con piani in attesa '
        'e utenti assegnati senza piano del mese corrente, includendo anche approvati e auto-approvazione.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Esegue anche se oggi non e il primo giorno del mese')
        parser.add_argument('--dry-run', action='store_true', help='Simula invio senza inviare email reali')
        parser.add_argument('--date', dest='as_of_date', help='Data di riferimento YYYY-MM-DD (default: data server locale)')

    @staticmethod
    def _sender_from_env() -> Optional[str]:
        from_email = (get_runtime_setting('DEFAULT_FROM_EMAIL', '') or '').strip()
        from_name = (get_runtime_setting('AGILE_EMAIL_FROM_NAME', '') or '').strip()
        if not from_email:
            return None
        if not from_name:
            return from_email
        return formataddr((from_name, from_email))

    @staticmethod
    def _month_name_year_it(year: int, month: int) -> str:
        month_names = [
            'gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno',
            'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre',
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

        if not force and today.day != 1:
            self.stdout.write(
                self.style.WARNING(f'Oggi {today.isoformat()} non e il primo giorno del mese, nessuna email inviata')
            )
            return

        target_year = today.year
        target_month = today.month
        month_label = f'{target_month:02d}/{target_year}'
        month_name_year = self._month_name_year_it(target_year, target_month)

        managed_users = User.objects.filter(
            manager__isnull=False,
            is_active=True,
            aila_subscribed=True,
        ).select_related('manager')

        manager_to_users: dict[int, list[User]] = {}
        for user in managed_users:
            manager_to_users.setdefault(user.manager_id, []).append(user)

        sent = 0
        skipped = 0
        errors = 0

        for manager_id, users in manager_to_users.items():
            manager = users[0].manager
            if not manager:
                skipped += 1
                continue
            manager_email = (manager.email or '').strip()
            if not manager_email:
                skipped += 1
                self.stdout.write(f'Salto manager {manager.username}: email assente')
                continue

            already_sent = AuditLog.objects.filter(
                actor=None,
                action='manager_monthly_summary_sent',
                target_type='User',
                target_id=manager.id,
                metadata__year=target_year,
                metadata__month=target_month,
            ).exists()
            if already_sent:
                skipped += 1
                self.stdout.write(f'Riepilogo gia inviato a {manager_email} per {month_label}, salto')
                continue

            managed_ids = [u.id for u in users]
            plans = MonthlyPlan.objects.filter(user_id__in=managed_ids, year=target_year, month=target_month).select_related('user')
            plan_by_user = {p.user_id: p for p in plans}

            pending = [p for p in plans if p.status == MonthlyPlan.Status.SUBMITTED]
            approved = [p for p in plans if p.status == MonthlyPlan.Status.APPROVED]
            missing = [u for u in users if u.id not in plan_by_user]
            auto_approve_users = [u for u in users if bool(u.auto_approve)]

            if not pending and not missing and not approved and not auto_approve_users:
                skipped += 1
                continue

            pending_lines = '\n'.join(
                [
                    f"- {((p.user.first_name or '').strip() + ' ' + (p.user.last_name or '').strip()).strip() or p.user.username} "
                    f"({p.user.username})"
                    for p in pending
                ]
            ) or '- Nessuno'
            missing_lines = '\n'.join(
                [
                    f"- {((u.first_name or '').strip() + ' ' + (u.last_name or '').strip()).strip() or u.username} "
                    f"({u.username})"
                    for u in missing
                ]
            ) or '- Nessuno'
            approved_lines = '\n'.join(
                [
                    f"- {((p.user.first_name or '').strip() + ' ' + (p.user.last_name or '').strip()).strip() or p.user.username} "
                    f"({p.user.username})"
                    for p in approved
                ]
            ) or '- Nessuno'
            auto_approve_lines = '\n'.join(
                [
                    f"- {((u.first_name or '').strip() + ' ' + (u.last_name or '').strip()).strip() or u.username} "
                    f"({u.username})"
                    for u in auto_approve_users
                ]
            ) or '- Nessuno'

            manager_name = f'{(manager.first_name or "").strip()} {(manager.last_name or "").strip()}'.strip() or manager.username
            default_subject = f'Riepilogo richieste e piani - {month_name_year}'
            links = build_email_link_context()
            portal_line = f"Link portale: {links['portal_url']}\n\n" if links['portal_url'] else ''
            default_body = (
                'Gentile {manager_name},\n\n'
                'Riepilogo per {month_name_year}.\n\n'
                'Piani in attesa di approvazione ({pending_count}):\n'
                '{pending_lines}\n\n'
                'Piani approvati ({approved_count}):\n'
                '{approved_lines}\n\n'
                'Utenti senza piano del mese ({missing_count}):\n'
                '{missing_lines}\n\n'
                'Utenti in auto-approvazione ({auto_approve_count}):\n'
                '{auto_approve_lines}\n\n'
                '{portal_line}'
                'Puoi accedere al portale per gestire le richieste.'
            )
            subject, body = self._render_from_template(
                key=SystemEmailTemplate.Key.MANAGER_MONTHLY_SUMMARY,
                default_subject=default_subject,
                default_body=default_body,
                context={
                    'manager_name': manager_name,
                    'month_label': month_label,
                    'month_name_year': month_name_year,
                    'pending_count': len(pending),
                    'approved_count': len(approved),
                    'missing_count': len(missing),
                    'auto_approve_count': len(auto_approve_users),
                    'pending_lines': pending_lines,
                    'approved_lines': approved_lines,
                    'missing_lines': missing_lines,
                    'auto_approve_lines': auto_approve_lines,
                    'portal_line': portal_line,
                    **links,
                },
            )

            if dry_run:
                self.stdout.write(f'[DRY-RUN] -> {manager_email} | {subject}')
                sent += 1
                continue

            try:
                send_mail(
                    subject=subject,
                    message=body,
                    from_email=self._sender_from_env(),
                    recipient_list=[manager_email],
                    fail_silently=False,
                )
                AuditLog.track(
                    actor=None,
                    action='manager_monthly_summary_sent',
                    target_type='User',
                    target_id=manager.id,
                    metadata={
                        'year': target_year,
                        'month': target_month,
                        'email': manager_email,
                        'pending_count': len(pending),
                        'approved_count': len(approved),
                        'missing_count': len(missing),
                        'auto_approve_count': len(auto_approve_users),
                    },
                )
                sent += 1
                self.stdout.write(self.style.SUCCESS(f'Riepilogo inviato a {manager_email}'))
            except Exception as exc:
                errors += 1
                self.stderr.write(self.style.ERROR(f'Errore invio a {manager_email}: {exc}'))

        suffix = ' (dry-run)' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(f'Riepilogo referenti completato: inviati={sent}, saltati={skipped}, errori={errors}{suffix}')
        )
