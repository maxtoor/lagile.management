from django.contrib import admin
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import Group
from django.contrib import messages
from django.contrib.admin.utils import unquote
from django.conf import settings
from django.core.management import call_command
from django.core.mail import send_mail
from django import forms
from django.db.models import Q
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
import io
import os
import subprocess
import tempfile
from datetime import date
from collections import deque
from pathlib import Path
from email.utils import formataddr
import re

from .models import AppSetting, AgileGroup, AuditLog, ChangeRequest, DepartmentPolicy, Holiday, MonthlyPlan, PlanDay, SystemEmailTemplate, User
from .runtime_settings import build_runtime_ui_context, get_runtime_setting

admin.site.site_title = 'LAgile.Management'
admin.site.site_header = 'LAgile.Management'
admin.site.index_title = 'Amministrazione applicazione'


class CollapseMediaMixin:
    class Media:
        css = {
            'all': ('agile/admin-user-collapse.css',),
        }


class ManagerChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user_obj):
        full_name = f'{(user_obj.first_name or "").strip()} {(user_obj.last_name or "").strip()}'.strip()
        return f'{user_obj.username} ({full_name})' if full_name else user_obj.username


class CustomUserAdminForm(UserChangeForm):
    user_approved = forms.ChoiceField(
        label='Utente approvato',
        choices=(('1', 'Sì'), ('0', 'No')),
        widget=forms.Select,
        initial='1',
        required=True,
    )
    aila_subscribed = forms.ChoiceField(
        label='Sottoscrizione AILA',
        choices=(('0', 'No'), ('1', 'Sì')),
        widget=forms.Select,
        initial='0',
        required=True,
    )
    auto_approve = forms.ChoiceField(
        label='Approvazione automatica',
        choices=(('0', 'No'), ('1', 'Sì')),
        widget=forms.Select,
        initial='0',
        required=True,
    )
    manager = ManagerChoiceField(
        queryset=User.objects.none(),
        required=False,
        label='Responsabile approvazione',
    )

    class Meta:
        model = User
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and getattr(self.instance, 'pk', None):
            if 'user_approved' in self.fields:
                current = not bool(getattr(self.instance, 'onboarding_pending', False))
                value = '1' if current else '0'
                self.fields['user_approved'].initial = value
                self.initial['user_approved'] = value
            if 'aila_subscribed' in self.fields:
                current = bool(getattr(self.instance, 'aila_subscribed', False))
                value = '1' if current else '0'
                self.fields['aila_subscribed'].initial = value
                self.initial['aila_subscribed'] = value
            if 'auto_approve' in self.fields:
                current = bool(getattr(self.instance, 'auto_approve', False))
                value = '1' if current else '0'
                self.fields['auto_approve'].initial = value
                self.initial['auto_approve'] = value
        if 'manager' in self.fields:
            self.fields['manager'].queryset = User.objects.filter(
                Q(role__in=['ADMIN', 'SUPERADMIN']) | Q(is_superuser=True)
            ).order_by('first_name', 'last_name', 'username')

    def clean_aila_subscribed(self):
        value = str(self.cleaned_data.get('aila_subscribed', '0')).strip()
        return value == '1'

    def clean_auto_approve(self):
        value = str(self.cleaned_data.get('auto_approve', '0')).strip()
        return value == '1'

    def clean_user_approved(self):
        value = str(self.cleaned_data.get('user_approved', '1')).strip()
        return value == '1'

    def clean(self):
        cleaned = super().clean()
        if 'user_approved' in cleaned:
            cleaned['onboarding_pending'] = not bool(cleaned['user_approved'])
        return cleaned


@admin.register(User)
class CustomUserAdmin(CollapseMediaMixin, UserAdmin):
    form = CustomUserAdminForm
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (
            'Informazioni personali',
            {
                'classes': ('collapse',),
                'fields': ('first_name', 'last_name', 'email'),
            },
        ),
        (
            'Impostazioni applicazione',
            {
                'classes': ('collapse',),
                'fields': ('user_approved', 'department', 'role', 'aila_subscribed', 'auto_approve', 'manager'),
            },
        ),
        (
            'Permessi',
            {
                'classes': ('collapse',),
                'fields': (
                    'is_active',
                    'is_staff',
                    'is_superuser',
                    'groups',
                    'user_permissions',
                ),
            },
        ),
        (
            'Date importanti',
            {
                'classes': ('collapse',),
                'fields': ('last_login', 'date_joined'),
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': ('username', 'password1', 'password2'),
            },
        ),
    )
    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'department',
        'role',
        'aila_subscribed',
        'onboarding_pending',
        'auto_approve',
        'manager',
        'is_active',
    )
    list_filter = ('role', 'aila_subscribed', 'onboarding_pending', 'auto_approve', 'department', 'manager', 'is_active')

    @staticmethod
    def _local_superusers_queryset():
        return User.objects.filter(is_superuser=True, is_active=True).exclude(password__startswith='!')

    def _blocked_local_superuser_ids(self, queryset):
        local_superuser_ids = set(self._local_superusers_queryset().values_list('id', flat=True))
        selected_ids = set(queryset.values_list('id', flat=True))
        selected_local_superuser_ids = selected_ids & local_superuser_ids
        blocked_ids = set()
        if selected_local_superuser_ids and not (local_superuser_ids - selected_local_superuser_ids):
            # Mantiene almeno un superuser locale attivo.
            blocked_ids.add(sorted(selected_local_superuser_ids)[0])
        return blocked_ids

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj=obj)

    def delete_view(self, request, object_id, extra_context=None):
        obj = self.get_object(request, unquote(object_id))
        if obj and obj.is_superuser and not self._local_superusers_queryset().exclude(pk=obj.pk).exists():
            messages.error(request, 'Operazione bloccata: deve restare almeno un superuser locale attivo.')
            return redirect('admin:agile_user_change', obj.pk)
        return super().delete_view(request, object_id, extra_context=extra_context)

    def get_deleted_objects(self, objs, request):
        queryset = objs if hasattr(objs, 'values_list') else User.objects.filter(pk__in=[obj.pk for obj in objs])
        blocked_ids = self._blocked_local_superuser_ids(queryset)
        if blocked_ids:
            messages.warning(
                request,
                "Nella selezione e presente l'ultimo superuser locale attivo: non verra incluso nella cancellazione.",
            )
            queryset = queryset.exclude(id__in=blocked_ids)
            objs = queryset
        return super().get_deleted_objects(objs, request)

    def delete_queryset(self, request, queryset):
        blocked_ids = self._blocked_local_superuser_ids(queryset)
        blocked = len(blocked_ids)
        if blocked:
            messages.warning(
                request,
                f'Cancellazione protetta: {blocked} utente superuser locale non e stato eliminato per mantenere almeno un superuser locale attivo.',
            )
        deletable = queryset.exclude(id__in=blocked_ids)
        if deletable.exists():
            super().delete_queryset(request, deletable)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if not obj or obj.has_usable_password():
            return fieldsets

        normalized = []
        for name, opts in fieldsets:
            fields = tuple(opts.get('fields', ()))
            if name is None and 'password' in fields:
                fields = tuple(field for field in fields if field != 'password')
            normalized.append((name, {**opts, 'fields': fields}))
        return tuple(normalized)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == 'manager' and formfield:
            # Nasconde le icone relazione (+ / matita / cestino / vista) sul campo referente.
            widget = formfield.widget
            if hasattr(widget, 'can_add_related'):
                widget.can_add_related = False
            if hasattr(widget, 'can_change_related'):
                widget.can_change_related = False
            if hasattr(widget, 'can_delete_related'):
                widget.can_delete_related = False
            if hasattr(widget, 'can_view_related'):
                widget.can_view_related = False
        return formfield


class ImportLdapAdminForm(forms.Form):
    ldap_filter = forms.CharField(
        label='Filtro LDAP',
        required=False,
        help_text='Lascia vuoto per usare LDAP_IMPORT_FILTER da .env',
    )
    base_dn = forms.CharField(
        label='Base DN',
        required=False,
        help_text='Lascia vuoto per usare LDAP_USER_BASE_DN da .env',
    )
    dry_run = forms.BooleanField(
        label='Dry run',
        required=False,
        initial=True,
    )


class SyncLdapAdminForm(forms.Form):
    ldap_filter = forms.CharField(
        label='Filtro LDAP',
        required=False,
        help_text='Lascia vuoto per usare LDAP_IMPORT_FILTER da .env',
    )
    base_dn = forms.CharField(
        label='Base DN',
        required=False,
        help_text='Lascia vuoto per usare LDAP_USER_BASE_DN da .env',
    )
    deactivate_missing = forms.BooleanField(
        label='Disattiva assenti in LDAP',
        required=False,
        initial=False,
    )
    create_missing = forms.BooleanField(
        label='Crea utenti mancanti in locale',
        required=False,
        initial=False,
    )
    dry_run = forms.BooleanField(
        label='Dry run',
        required=False,
        initial=True,
    )


class ImportCsvAdminForm(forms.Form):
    csv_file = forms.FileField(label='Backup CSV ICB')
    leaves_report_csv = forms.FileField(label='Leaves report CSV legacy')
    with_ldap_sync = forms.BooleanField(
        label='Esegui anche sync LDAP inline (nome, cognome, email)',
        required=False,
        initial=False,
    )
    overwrite_existing_plans = forms.BooleanField(
        label='Sovrascrivi eventuali piani gia presenti',
        required=False,
        initial=True,
    )
    import_notes = forms.BooleanField(
        label='Importa anche le note attivita dal leaves report',
        required=False,
        initial=True,
    )
    overwrite_notes = forms.BooleanField(
        label='Sovrascrivi anche note gia presenti',
        required=False,
        initial=False,
    )
    dry_run = forms.BooleanField(label='Dry run', required=False, initial=True)


class ExportReleaseAdminForm(forms.Form):
    indent = forms.IntegerField(
        label='Indentazione JSON',
        required=False,
        initial=2,
        min_value=0,
        max_value=8,
    )


class ImportReleaseAdminForm(forms.Form):
    json_file = forms.FileField(label='File JSON export')
    mode = forms.ChoiceField(
        label='Modalita import',
        choices=(('merge', 'Merge (upsert)'), ('replace', 'Replace (configurazioni)')),
        required=True,
        initial='merge',
    )
    dry_run = forms.BooleanField(
        label='Dry run',
        required=False,
        initial=True,
    )


class SyncHolidaysAdminForm(forms.Form):
    year = forms.IntegerField(label='Anno', required=True, initial=date.today().year, min_value=2000, max_value=2100)
    overwrite = forms.BooleanField(
        label='Aggiorna festivita gia presenti',
        required=False,
        initial=False,
    )


class SendTestEmailForm(forms.Form):
    recipient = forms.EmailField(label='Destinatario test')


@admin.register(AppSetting)
class AppSettingAdmin(CollapseMediaMixin, admin.ModelAdmin):
    fieldsets = (
        (
            'Portale',
            {
                'fields': ('date_display_format', 'login_logo_url', 'company_name', 'copyright_year'),
            },
        ),
        (
            'Email',
            {
                'classes': ('collapse',),
                'fields': ('default_from_email', 'email_from_name'),
            },
        ),
        (
            'Reminder e sommari',
            {
                'classes': ('collapse',),
                'fields': ('submission_reminder_offset_days', 'manager_monthly_summary_offset_days'),
            },
        ),
        (
            'Aggiornamento',
            {
                'classes': ('collapse',),
                'fields': ('updated_at',),
            },
        ),
    )
    readonly_fields = ('updated_at',)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        if AppSetting.objects.exists():
            return False
        return super().has_add_permission(request)

    def changelist_view(self, request, extra_context=None):
        obj = AppSetting.objects.order_by('id').first()
        if obj:
            return redirect('admin:agile_appsetting_change', obj.pk)
        return redirect('admin:agile_appsetting_add')

    def get_model_perms(self, request):
        # Accesso dalla sezione Strumenti nella home admin.
        return {}


@admin.register(AgileGroup)
class AgileGroupAdmin(GroupAdmin):
    pass


def _read_log_tail(log_path: str, lines: int) -> tuple[str, str | None]:
    target = Path(log_path)
    if not target.exists():
        return '', f'File log non trovato: {target}'
    if not target.is_file():
        return '', f'Percorso non valido: {target}'

    try:
        with target.open('r', encoding='utf-8', errors='replace') as handle:
            tail_lines = deque(handle, maxlen=lines)
    except OSError as exc:
        return '', f'Errore lettura file log: {exc}'

    return ''.join(tail_lines), None


def _get_log_sources() -> tuple[list[dict], str]:
    raw_sources = (getattr(settings, 'AGILE_LOG_MONITOR_SOURCES', '') or '').strip()
    fallback_path = (getattr(settings, 'AGILE_LOG_MONITOR_FILE', '') or '').strip()
    options: list[dict] = []
    selected_default = ''

    for item in raw_sources.split(';'):
        token = item.strip()
        if not token:
            continue
        if ':' not in token:
            continue
        key, path_value = token.split(':', 1)
        key = key.strip()
        path_value = path_value.strip()
        if not key or not path_value:
            continue
        options.append({'key': key, 'label': key, 'path': path_value})

    if not options and fallback_path:
        options.append({'key': 'app', 'label': 'app', 'path': fallback_path})

    if options:
        selected_default = options[0]['key']

    return options, selected_default


def _resolve_log_source_key(raw_key: str | None) -> tuple[str, str, list[dict]]:
    sources, default_key = _get_log_sources()
    selected_key = (raw_key or '').strip() or default_key
    if not sources:
        return selected_key, '', []

    source_map = {src['key']: src for src in sources}
    if selected_key not in source_map:
        selected_key = default_key
    return selected_key, source_map[selected_key]['path'], sources


def _run_update_check(*, fetch_remote: bool) -> list[str]:
    lines: list[str] = []
    repo_dir = Path(getattr(settings, 'BASE_DIR', '/app'))
    if not (repo_dir / '.git').exists():
        return ['Controllo aggiornamenti non disponibile: repository git non trovato.']

    git_cmd = ['git', '-C', str(repo_dir)]
    try:
        local_branch = subprocess.check_output(git_cmd + ['rev-parse', '--abbrev-ref', 'HEAD'], text=True).strip()
        local_head = subprocess.check_output(git_cmd + ['rev-parse', '--short', 'HEAD'], text=True).strip()
        remote_url = subprocess.check_output(git_cmd + ['remote', 'get-url', 'origin'], text=True).strip()
    except FileNotFoundError:
        return ['Controllo aggiornamenti non disponibile: comando "git" non presente nel container applicativo.']
    except subprocess.CalledProcessError as exc:
        return [f'Errore controllo git locale: {exc}']

    lines.append(f'Repo: {repo_dir}')
    lines.append(f'Remote: {remote_url}')
    lines.append(f'Branch locale: {local_branch}')
    lines.append(f'Commit locale: {local_head}')

    if fetch_remote:
        try:
            subprocess.check_call(
                git_cmd + ['fetch', 'origin', local_branch, '--quiet'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            lines.append('Fetch remoto: OK')
        except FileNotFoundError:
            lines.append('Fetch remoto: comando "git" non disponibile nel container.')
            return lines
        except subprocess.CalledProcessError as exc:
            lines.append(f'Fetch remoto: ERRORE ({exc})')
            return lines

    remote_ref = f'origin/{local_branch}'
    try:
        remote_head = subprocess.check_output(git_cmd + ['rev-parse', '--short', remote_ref], text=True).strip()
        counts = subprocess.check_output(git_cmd + ['rev-list', '--left-right', '--count', f'HEAD...{remote_ref}'], text=True).strip()
    except subprocess.CalledProcessError:
        lines.append(f'Riferimento remoto non disponibile: {remote_ref}')
        return lines

    try:
        ahead_count_str, behind_count_str = counts.split()
        ahead_count = int(ahead_count_str)
        behind_count = int(behind_count_str)
    except Exception:
        ahead_count = 0
        behind_count = 0

    lines.append(f'Commit remoto ({remote_ref}): {remote_head}')
    lines.append(f'Stato sync: ahead={ahead_count}, behind={behind_count}')

    if ahead_count == 0 and behind_count == 0:
        lines.append('Esito: il codice locale e allineato al remoto.')
    elif behind_count > 0:
        lines.append('Esito: aggiornamento disponibile (locale indietro rispetto al remoto).')
    elif ahead_count > 0:
        lines.append('Esito: il locale contiene commit non presenti sul remoto.')
    else:
        lines.append('Esito: divergenza locale/remoto.')

    return lines


def _extract_counter_pairs(text: str) -> list[tuple[str, str]]:
    return [(key.strip(), value.strip()) for key, value in re.findall(r'([a-zA-Z0-9_]+)\s*=\s*([^,]+)', text)]


def _prettify_counter_key(key: str) -> str:
    label = str(key or '').replace('_', ' ').strip()
    return label[:1].upper() + label[1:] if label else ''


def _build_preview_blocks(output_text: str, *, kind: str) -> list[dict]:
    blocks: list[dict] = []
    lines = [line.strip() for line in str(output_text or '').splitlines() if line.strip()]
    if not lines:
        return blocks

    if kind == 'release':
        for line in lines:
            if ':' not in line:
                continue
            title, payload = line.split(':', 1)
            pairs = _extract_counter_pairs(payload)
            if not pairs:
                continue
            blocks.append(
                {
                    'title': title.strip(),
                    'items': [{'label': _prettify_counter_key(key), 'value': value} for key, value in pairs],
                }
            )
        return blocks

    if kind == 'csv':
        users_updated = ''
        users_created = ''
        users_not_found = ''
        is_dry_run = False
        for line in lines:
            if line.startswith('UTENTI_AGGIORNATI:'):
                users_updated = line.split(':', 1)[1].strip()
            elif line.startswith('UTENTI_CREATI:'):
                users_created = line.split(':', 1)[1].strip()
            elif line.startswith('UTENTI_NON_TROVATI:'):
                users_not_found = line.split(':', 1)[1].strip()

        for line in reversed(lines):
            if 'Aggiornamento sedi da CSV completato' not in line:
                continue
            payload = line.split(':', 1)[1] if ':' in line else line
            if '(dry-run' in payload.lower():
                is_dry_run = True
                payload = re.sub(r'\s*\(dry-run[^)]*\)\s*$', '', payload, flags=re.IGNORECASE)
            pairs = _extract_counter_pairs(payload)
            if not pairs:
                break
            blocks.append(
                {
                    'title': 'Riepilogo import CSV ICB',
                    'items': [{'label': _prettify_counter_key(key), 'value': value} for key, value in pairs],
                }
            )
            break
        if users_updated or users_created or users_not_found:
            blocks.append(
                {
                    'title': 'Dettaglio utenti',
                    'items': [
                        {'label': 'Utenti aggiornati', 'value': users_updated or '-'},
                        {'label': 'Utenti creati', 'value': users_created or '-'},
                        {'label': 'Utenti non trovati', 'value': users_not_found or '-'},
                        {'label': 'Modalita', 'value': 'Dry-run' if is_dry_run else 'Import reale'},
                    ],
                }
            )
    return blocks


def import_tools_view(request):
    icb_legacy_enabled = bool(getattr(settings, 'ICB_LEGACY', False))

    if not request.user.is_superuser:
        messages.error(request, 'Accesso consentito solo ai superuser')
        return TemplateResponse(
            request,
            'admin/agile/import_tools.html',
            {
                **admin.site.each_context(request),
                'title': 'Import / Export dati',
                'csv_form': ImportCsvAdminForm(),
                'release_export_form': ExportReleaseAdminForm(),
                'release_import_form': ImportReleaseAdminForm(),
                'icb_legacy_enabled': icb_legacy_enabled,
                'logs': [],
            },
        )

    logs = []
    preview_blocks = []
    csv_form = ImportCsvAdminForm(prefix='csv')
    release_export_form = ExportReleaseAdminForm(prefix='release_export')
    release_import_form = ImportReleaseAdminForm(prefix='release_import')

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'clear_preview':
            logs = []
            preview_blocks = []
            csv_form = ImportCsvAdminForm(prefix='csv')
            release_export_form = ExportReleaseAdminForm(prefix='release_export')
            release_import_form = ImportReleaseAdminForm(prefix='release_import')
            messages.info(request, 'Anteprima e output azzerati')
        elif action in {'csv', 'csv_preview'}:
            if not icb_legacy_enabled:
                messages.error(request, 'Sezione ICB legacy disabilitata. Impostare ICB_LEGACY=1 per abilitarla.')
                logs.append('Azione bloccata: ICB legacy disabilitata (ICB_LEGACY=0).')
                csv_form = ImportCsvAdminForm(prefix='csv')
            else:
                csv_form = ImportCsvAdminForm(request.POST, request.FILES, prefix='csv')
                if csv_form.is_valid():
                    uploaded = csv_form.cleaned_data['csv_file']
                    uploaded_leaves = csv_form.cleaned_data['leaves_report_csv']
                    out = io.StringIO()
                    err = io.StringIO()
                    tmp_path = None
                    tmp_leaves_path = None
                    try:
                        suffix = os.path.splitext(uploaded.name or '')[1] or '.csv'
                        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                            for chunk in uploaded.chunks():
                                tmp_file.write(chunk)
                            tmp_path = tmp_file.name

                        leaves_suffix = os.path.splitext(uploaded_leaves.name or '')[1] or '.csv'
                        with tempfile.NamedTemporaryFile(delete=False, suffix=leaves_suffix) as tmp_file:
                            for chunk in uploaded_leaves.chunks():
                                tmp_file.write(chunk)
                            tmp_leaves_path = tmp_file.name

                        kwargs = {
                            'dry_run': bool(csv_form.cleaned_data.get('dry_run')),
                            'with_ldap_sync': bool(csv_form.cleaned_data.get('with_ldap_sync')),
                            'overwrite_existing_plans': bool(csv_form.cleaned_data.get('overwrite_existing_plans')),
                            'leaves_report_csv': [tmp_leaves_path],
                        }
                        if action == 'csv_preview':
                            kwargs['dry_run'] = True

                        call_command('import_icb_legacy_bundle', tmp_path, stdout=out, stderr=err, **kwargs)

                        if csv_form.cleaned_data.get('import_notes'):
                            notes_kwargs = {
                                'backup_csv_path': tmp_path,
                                'dry_run': kwargs['dry_run'],
                            }
                            if csv_form.cleaned_data.get('overwrite_notes'):
                                notes_kwargs['overwrite'] = True
                            call_command(
                                'import_legacy_icb_notes',
                                tmp_leaves_path,
                                stdout=out,
                                stderr=err,
                                **notes_kwargs,
                            )

                        output = (out.getvalue() + '\n' + err.getvalue()).strip()
                        logs.append(output or 'Import bundle ICB completato')
                        if action == 'csv_preview':
                            messages.info(request, 'Anteprima import bundle ICB completata (dry-run)')
                        else:
                            messages.success(request, 'Import bundle ICB eseguito')
                    except Exception as exc:
                        output = (out.getvalue() + '\n' + err.getvalue()).strip()
                        if output:
                            logs.append(output)
                        logs.append(str(exc))
                        messages.error(request, f'Errore import bundle ICB: {exc}')
                    finally:
                        if tmp_path and os.path.exists(tmp_path):
                            try:
                                os.unlink(tmp_path)
                            except OSError:
                                pass
                        if tmp_leaves_path and os.path.exists(tmp_leaves_path):
                            try:
                                os.unlink(tmp_leaves_path)
                            except OSError:
                                pass
                else:
                    error_text = '; '.join(
                        [f'{field}: {", ".join(errors)}' for field, errors in csv_form.errors.items()]
                    ) or 'Dati non validi'
                    logs.append(f'Errore validazione bundle ICB: {error_text}')
                    messages.error(request, f'Errore import bundle ICB: {error_text}')
        elif action == 'release_export':
            release_export_form = ExportReleaseAdminForm(request.POST, prefix='release_export')
            if release_export_form.is_valid():
                out = io.StringIO()
                err = io.StringIO()
                tmp_path = None
                try:
                    indent = int(release_export_form.cleaned_data.get('indent') or 2)
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.json') as tmp_file:
                        tmp_path = tmp_file.name
                    call_command('export_release_data', tmp_path, indent=indent, stdout=out, stderr=err)

                    payload = Path(tmp_path).read_bytes()
                    filename = f'release-export-{date.today().isoformat()}.json'
                    response = HttpResponse(payload, content_type='application/json; charset=utf-8')
                    response['Content-Disposition'] = f'attachment; filename="{filename}"'
                    return response
                except Exception as exc:
                    output = (out.getvalue() + '\n' + err.getvalue()).strip()
                    if output:
                        logs.append(output)
                    logs.append(str(exc))
                    messages.error(request, f'Errore export release: {exc}')
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass
        elif action in {'release_import', 'release_preview'}:
            release_import_form = ImportReleaseAdminForm(request.POST, request.FILES, prefix='release_import')
            if release_import_form.is_valid():
                uploaded = release_import_form.cleaned_data['json_file']
                out = io.StringIO()
                err = io.StringIO()
                tmp_path = None
                try:
                    suffix = os.path.splitext(uploaded.name or '')[1] or '.json'
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                        for chunk in uploaded.chunks():
                            tmp_file.write(chunk)
                        tmp_path = tmp_file.name

                    kwargs = {
                        'mode': (release_import_form.cleaned_data.get('mode') or 'merge').strip(),
                        'dry_run': bool(release_import_form.cleaned_data.get('dry_run')),
                    }
                    if action == 'release_preview':
                        kwargs['dry_run'] = True
                    call_command('import_release_data', tmp_path, stdout=out, stderr=err, **kwargs)
                    output = (out.getvalue() + '\n' + err.getvalue()).strip()
                    logs.append(output or 'Import release completato')
                    if action == 'release_preview':
                        preview_blocks = _build_preview_blocks(output, kind='release')
                        messages.info(request, 'Anteprima impatti release completata (dry-run)')
                    elif kwargs['dry_run']:
                        messages.info(request, 'Dry-run import release completato')
                    else:
                        messages.success(request, 'Import release eseguito')
                except Exception as exc:
                    output = (out.getvalue() + '\n' + err.getvalue()).strip()
                    if output:
                        logs.append(output)
                    logs.append(str(exc))
                    messages.error(request, f'Errore import release: {exc}')
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass
            else:
                error_text = '; '.join(
                    [f'{field}: {", ".join(errors)}' for field, errors in release_import_form.errors.items()]
                ) or 'Dati non validi'
                logs.append(f'Errore validazione import release: {error_text}')
                messages.error(request, f'Errore import release: {error_text}')

    return TemplateResponse(
        request,
        'admin/agile/import_tools.html',
        {
            **admin.site.each_context(request),
            'title': 'Import / Export dati',
            'csv_form': csv_form,
            'release_export_form': release_export_form,
            'release_import_form': release_import_form,
            'logs': logs,
            'preview_blocks': preview_blocks,
            'is_superuser': request.user.is_superuser,
            'icb_legacy_enabled': icb_legacy_enabled,
            'opts': User._meta,
        },
    )


def log_monitor_view(request):
    if not request.user.is_staff:
        messages.error(request, 'Accesso consentito solo agli utenti staff')
        return TemplateResponse(
            request,
            'admin/agile/log_monitor.html',
            {
                **admin.site.each_context(request),
                'title': 'Monitor log',
                'log_lines': '',
                'log_error': 'Permessi insufficienti',
                'log_path': '',
                'selected_source': '',
                'log_sources': [],
                'poll_url': '',
                'refresh_seconds': 3,
                'default_lines': 200,
                'opts': User._meta,
            },
        )

    default_lines = 200
    selected_source, log_path, sources = _resolve_log_source_key(request.GET.get('source'))
    refresh_seconds = max(2, int(getattr(settings, 'AGILE_LOG_MONITOR_REFRESH_SECONDS', 3)))
    log_lines, log_error = _read_log_tail(log_path, default_lines)
    return TemplateResponse(
        request,
        'admin/agile/log_monitor.html',
        {
            **admin.site.each_context(request),
            'title': 'Monitor log',
            'log_lines': log_lines,
            'log_error': log_error,
            'log_path': log_path,
            'selected_source': selected_source,
            'log_sources': sources,
            'poll_url': reverse('admin:agile_log_monitor_data'),
            'refresh_seconds': refresh_seconds,
            'default_lines': default_lines,
            'opts': User._meta,
        },
    )


def log_monitor_data_view(request):
    if not request.user.is_staff:
        return JsonResponse({'ok': False, 'error': 'forbidden'}, status=403)

    raw_lines = request.GET.get('lines', '200')
    try:
        lines = int(raw_lines)
    except (TypeError, ValueError):
        lines = 200
    lines = max(50, min(lines, 2000))

    selected_source, log_path, sources = _resolve_log_source_key(request.GET.get('source'))
    content, error = _read_log_tail(log_path, lines)
    return JsonResponse(
        {
            'ok': error is None,
            'source': selected_source,
            'sources': [{'key': item['key'], 'label': item['label']} for item in sources],
            'path': log_path,
            'lines': lines,
            'error': error,
            'content': content,
        }
    )


def _extend_admin_urls(get_urls):
    def wrapped_urls():
        custom_urls = [
            path(
                'agile/import-tools/',
                admin.site.admin_view(import_tools_view),
                name='agile_import_tools',
            ),
            path(
                'agile/log-monitor/',
                admin.site.admin_view(log_monitor_view),
                name='agile_log_monitor',
            ),
            path(
                'agile/log-monitor/data/',
                admin.site.admin_view(log_monitor_data_view),
                name='agile_log_monitor_data',
            ),
        ]
        return custom_urls + get_urls()

    return wrapped_urls


def _extend_admin_each_context(each_context):
    def wrapped_each_context(request):
        context = each_context(request)
        context.update(build_runtime_ui_context())
        return context

    return wrapped_each_context


if not getattr(admin.site, '_agile_import_tools_patched', False):
    try:
        admin.site.unregister(Group)
    except admin.sites.NotRegistered:
        pass
    admin.site.get_urls = _extend_admin_urls(admin.site.get_urls)
    admin.site._agile_import_tools_patched = True

if not getattr(admin.site, '_agile_each_context_patched', False):
    admin.site.each_context = _extend_admin_each_context(admin.site.each_context)
    admin.site._agile_each_context_patched = True


class PlanDayInline(admin.TabularInline):
    model = PlanDay
    extra = 0
    classes = ('collapse',)


@admin.register(MonthlyPlan)
class MonthlyPlanAdmin(CollapseMediaMixin, admin.ModelAdmin):
    fieldsets = (
        ('Piano', {'fields': ('user', 'year', 'month', 'status')}),
        (
            'Approvazione',
            {
                'classes': ('collapse',),
                'fields': ('submitted_at', 'approved_by', 'approved_at', 'rejection_reason'),
            },
        ),
        (
            'Snapshot approvato',
            {
                'classes': ('collapse',),
                'fields': ('approved_days_snapshot',),
            },
        ),
    )
    list_display = ('user', 'month', 'year', 'status', 'submitted_at', 'approved_by', 'approved_at')
    list_filter = ('status', 'year', 'month')
    search_fields = ('user__username', 'user__email')
    inlines = [PlanDayInline]


@admin.register(AuditLog)
class AuditLogAdmin(CollapseMediaMixin, admin.ModelAdmin):
    fieldsets = (
        (
            'Evento',
            {
                'fields': ('created_at', 'actor', 'action', 'target_type', 'target_id'),
            },
        ),
        (
            'Dettagli',
            {
                'classes': ('collapse',),
                'fields': ('metadata',),
            },
        ),
    )
    list_display = ('created_at', 'actor', 'action', 'target_type', 'target_id')
    list_filter = ('action', 'target_type', 'created_at')
    search_fields = ('actor__username', 'target_type', 'action')
    readonly_fields = ('created_at',)


@admin.register(DepartmentPolicy)
class DepartmentPolicyAdmin(CollapseMediaMixin, admin.ModelAdmin):
    fieldsets = (
        ('Regole', {'fields': ('department', 'max_remote_days', 'february_max_remote_days')}),
        (
            'Vincoli',
            {
                'classes': ('collapse',),
                'fields': ('require_on_site_prevalence',),
            },
        ),
    )
    list_display = ('department', 'max_remote_days', 'february_max_remote_days', 'require_on_site_prevalence')
    search_fields = ('department',)


@admin.register(Holiday)
class HolidayAdmin(CollapseMediaMixin, admin.ModelAdmin):
    list_display = ('day', 'name', 'department')
    list_filter = ('department',)
    search_fields = ('name', 'department')


@admin.register(ChangeRequest)
class ChangeRequestAdmin(CollapseMediaMixin, admin.ModelAdmin):
    fieldsets = (
        (
            'Richiesta',
            {
                'fields': ('created_at', 'user', 'plan', 'status', 'reason'),
            },
        ),
        (
            'Esito',
            {
                'classes': ('collapse',),
                'fields': ('processed_by', 'processed_at', 'response_reason'),
            },
        ),
    )
    list_display = ('created_at', 'user', 'plan', 'status', 'processed_by', 'processed_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'plan__user__username', 'reason')
    readonly_fields = ('created_at',)


@admin.register(SystemEmailTemplate)
class SystemEmailTemplateAdmin(CollapseMediaMixin, admin.ModelAdmin):
    fieldsets = (
        ('Template', {'fields': ('key', 'subject_template')}),
        (
            'Corpo',
            {
                'classes': ('collapse',),
                'fields': ('body_template',),
            },
        ),
        (
            'Legenda variabili',
            {
                'classes': ('collapse',),
                'fields': ('variable_legend',),
            },
        ),
        (
            'Test',
            {
                'classes': ('collapse',),
                'fields': ('test_email_tools',),
            },
        ),
        (
            'Aggiornamento',
            {
                'classes': ('collapse',),
                'fields': ('updated_at',),
            },
        ),
    )
    readonly_fields = ('updated_at', 'variable_legend', 'test_email_tools')
    list_display = ('key', 'updated_at')
    search_fields = ('key', 'subject_template', 'body_template')

    @admin.display(description='Variabili disponibili')
    def variable_legend(self, obj):
        return format_html(
            "<div>"
            "<strong>Generali:</strong> "
            "<code>{{first_name_or_username}}</code>, <code>{{first_name}}</code>, <code>{{last_name}}</code>, "
            "<code>{{full_name}}</code>, <code>{{username}}</code>, "
            "<code>{{month_label}}</code>, <code>{{month_name_year}}</code>, "
            "<code>{{status_label}}</code>, <code>{{status_label_lower}}</code>, "
            "<code>{{email}}</code>, <code>{{import_timestamp}}</code>"
            "<br><strong>Esiti:</strong> "
            "<code>{{change_reason}}</code>, <code>{{rejection_reason}}</code>, <code>{{final_line}}</code>"
            "<br><strong>Referente:</strong> "
            "<code>{{manager_name}}</code>, <code>{{employee_name}}</code>, "
            "<code>{{pending_count}}</code>, <code>{{missing_count}}</code>, "
            "<code>{{pending_lines}}</code>, <code>{{missing_lines}}</code>"
            "<br><strong>Link:</strong> "
            "<code>{{public_base_url}}</code>, <code>{{portal_url}}</code>, <code>{{admin_url}}</code>"
            "</div>"
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
    def _sample_context_for_key(key: str) -> dict:
        base = {
            'first_name': 'Mario',
            'last_name': 'Rossi',
            'full_name': 'Mario Rossi',
            'username': 'mrossi',
            'first_name_or_username': 'Mario',
            'manager_name': 'Luigi Bianchi',
            'employee_name': 'Mario Rossi',
            'month_label': '03/2026',
            'month_name_year': 'marzo 2026',
            'pending_count': 2,
            'missing_count': 1,
            'pending_lines': '- Mario Rossi (mrossi)\n- Anna Verdi (averdi)',
            'missing_lines': '- Paolo Neri (pneri)',
            'status_label': 'APPROVATA',
            'status_label_lower': 'approvata',
            'change_reason': 'Aggiornamento attivita su progetto sperimentale',
            'rejection_reason': 'Motivazione di esempio',
            'final_line': 'La variazione e stata recepita nel piano.',
            'email': 'mario.rossi@example.org',
            'import_timestamp': '2026-03-08 10:30:00',
            'public_base_url': 'https://lagile.example.org',
            'portal_url': 'https://lagile.example.org/',
            'admin_url': 'https://lagile.example.org/admin/',
        }
        if key == 'PLAN_APPROVED':
            base.update(
                {
                    'status_label': 'APPROVATO',
                    'status_label_lower': 'approvato',
                    'final_line': 'Il piano e ora definitivo.',
                }
            )
        elif key == 'PLAN_REJECTED':
            base.update(
                {
                    'status_label': 'RIFIUTATO',
                    'status_label_lower': 'rifiutato',
                    'final_line': 'Motivazione rifiuto: Motivazione di esempio',
                }
            )
        elif key == 'CHANGE_REJECTED':
            base.update(
                {
                    'status_label': 'RIFIUTATA',
                    'status_label_lower': 'rifiutata',
                    'final_line': 'Motivazione rifiuto: Motivazione di esempio',
                }
            )
        return base

    @staticmethod
    def _render_template(text: str, context: dict) -> str:
        class _SafeDict(dict):
            def __missing__(self, key):
                return '{' + str(key) + '}'

        try:
            return (text or '').format_map(_SafeDict(context or {}))
        except Exception:
            return text or ''

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                '<path:object_id>/send-test/',
                self.admin_site.admin_view(self.send_test_email_view),
                name='agile_systememailtemplate_send_test',
            ),
        ]
        return custom_urls + urls

    @admin.display(description='Invio test')
    def test_email_tools(self, obj):
        if not obj or not obj.pk:
            return 'Salva il template per abilitare il test email.'
        url = reverse('admin:agile_systememailtemplate_send_test', args=[obj.pk])
        return format_html('<a class="button" href="{}">Invia email di test</a>', url)

    def send_test_email_view(self, request, object_id):
        template_obj = get_object_or_404(SystemEmailTemplate, pk=object_id)

        if request.method == 'POST':
            form = SendTestEmailForm(request.POST)
            if form.is_valid():
                recipient = form.cleaned_data['recipient']
                context = self._sample_context_for_key(template_obj.key)
                subject = self._render_template(template_obj.subject_template, context)
                body = self._render_template(template_obj.body_template, context)
                try:
                    send_mail(
                        subject=subject,
                        message=body,
                        from_email=self._sender_from_env(),
                        recipient_list=[recipient],
                        fail_silently=False,
                    )
                    messages.success(request, f'Email di test inviata a {recipient}')
                    return redirect('admin:agile_systememailtemplate_change', object_id)
                except Exception as exc:
                    messages.error(request, f'Errore invio email test: {exc}')
        else:
            form = SendTestEmailForm(initial={'recipient': getattr(request.user, 'email', '') or ''})

        context = {
            **self.admin_site.each_context(request),
            'title': f'Invia test email - {template_obj.get_key_display()}',
            'opts': self.model._meta,
            'template_obj': template_obj,
            'form': form,
            'rendered_subject': self._render_template(template_obj.subject_template, self._sample_context_for_key(template_obj.key)),
            'rendered_body': self._render_template(template_obj.body_template, self._sample_context_for_key(template_obj.key)),
            'back_url': reverse('admin:agile_systememailtemplate_change', args=[template_obj.pk]),
        }
        return TemplateResponse(request, 'admin/agile/system_email_template_send_test.html', context)
