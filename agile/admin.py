from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.contrib import messages
from django.conf import settings
from django.core.management import call_command
from django.core.mail import send_mail
from django import forms
from django.db.models import Q
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from django.shortcuts import get_object_or_404, redirect
import io
import os
import tempfile
from email.utils import formataddr

from .models import AuditLog, ChangeRequest, DepartmentPolicy, Holiday, MonthlyPlan, PlanDay, SystemEmailTemplate, User


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
        label='Referente amministrativo',
    )

    class Meta:
        model = User
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'aila_subscribed' in self.fields:
            current = bool(getattr(self.instance, 'aila_subscribed', False))
            self.fields['aila_subscribed'].initial = '1' if current else '0'
        if 'auto_approve' in self.fields:
            current = bool(getattr(self.instance, 'auto_approve', False))
            self.fields['auto_approve'].initial = '1' if current else '0'
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
                'fields': ('department', 'role', 'aila_subscribed', 'auto_approve', 'manager'),
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
        'auto_approve',
        'manager',
        'is_active',
    )
    list_filter = ('role', 'aila_subscribed', 'auto_approve', 'department', 'manager', 'is_active')

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


class ImportCsvAdminForm(forms.Form):
    csv_file = forms.FileField(label='File CSV')
    email_column = forms.CharField(label='Colonna email', required=False, initial='email')
    lastname_column = forms.CharField(label='Colonna cognome', required=False, initial='lastname')
    site_column = forms.CharField(label='Colonna sede', required=False, initial='department')
    site_mode = forms.ChoiceField(
        label='Modalita sede',
        choices=(('exact', 'Valore completo'), ('last-word', 'Ultima parola')),
        required=False,
        initial='last-word',
    )
    fallback_lastname = forms.BooleanField(
        label='Fallback su cognome se email non trovata',
        required=False,
        initial=True,
    )
    import_groups = forms.BooleanField(
        label='Importa anche i gruppi',
        required=False,
        initial=False,
    )
    delimiter = forms.CharField(label='Separatore', required=False, initial=',', max_length=1)
    dry_run = forms.BooleanField(label='Dry run', required=False, initial=True)


class SendTestEmailForm(forms.Form):
    recipient = forms.EmailField(label='Destinatario test')


def import_tools_view(request):
    if not request.user.is_superuser:
        messages.error(request, 'Accesso consentito solo ai superuser')
        return TemplateResponse(
            request,
            'admin/agile/import_tools.html',
            {
                'title': 'Strumenti importazione',
                'ldap_form': ImportLdapAdminForm(),
                'csv_form': ImportCsvAdminForm(),
                'logs': [],
            },
        )

    logs = []
    ldap_form = ImportLdapAdminForm(prefix='ldap')
    csv_form = ImportCsvAdminForm(prefix='csv')

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        if action == 'ldap':
            ldap_form = ImportLdapAdminForm(request.POST, prefix='ldap')
            if ldap_form.is_valid():
                out = io.StringIO()
                err = io.StringIO()
                kwargs = {
                    'dry_run': bool(ldap_form.cleaned_data.get('dry_run')),
                }
                ldap_filter = (ldap_form.cleaned_data.get('ldap_filter') or '').strip()
                base_dn = (ldap_form.cleaned_data.get('base_dn') or '').strip()
                if ldap_filter:
                    kwargs['ldap_filter'] = ldap_filter
                if base_dn:
                    kwargs['base_dn'] = base_dn
                try:
                    call_command('import_ldap_users', stdout=out, stderr=err, **kwargs)
                    output = (out.getvalue() + '\n' + err.getvalue()).strip()
                    logs.append(output or 'Import LDAP completato')
                    messages.success(request, 'Import LDAP eseguito')
                except Exception as exc:
                    output = (out.getvalue() + '\n' + err.getvalue()).strip()
                    if output:
                        logs.append(output)
                    logs.append(str(exc))
                    messages.error(request, f'Errore import LDAP: {exc}')
        elif action == 'csv':
            csv_form = ImportCsvAdminForm(request.POST, request.FILES, prefix='csv')
            if csv_form.is_valid():
                uploaded = csv_form.cleaned_data['csv_file']
                out = io.StringIO()
                err = io.StringIO()
                tmp_path = None
                try:
                    suffix = os.path.splitext(uploaded.name or '')[1] or '.csv'
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
                        for chunk in uploaded.chunks():
                            tmp_file.write(chunk)
                        tmp_path = tmp_file.name

                    kwargs = {
                        'email_column': (csv_form.cleaned_data.get('email_column') or 'email').strip(),
                        'lastname_column': (csv_form.cleaned_data.get('lastname_column') or 'lastname').strip(),
                        'site_column': (csv_form.cleaned_data.get('site_column') or 'department').strip(),
                        'site_mode': (csv_form.cleaned_data.get('site_mode') or 'last-word').strip(),
                        'delimiter': (csv_form.cleaned_data.get('delimiter') or ',').strip()[:1] or ',',
                        'dry_run': bool(csv_form.cleaned_data.get('dry_run')),
                    }
                    if csv_form.cleaned_data.get('fallback_lastname'):
                        kwargs['fallback_lastname'] = True
                    if csv_form.cleaned_data.get('import_groups'):
                        kwargs['import_groups'] = True
                    call_command('update_user_sites_from_csv', tmp_path, stdout=out, stderr=err, **kwargs)
                    output = (out.getvalue() + '\n' + err.getvalue()).strip()
                    logs.append(output or 'Import CSV completato')
                    messages.success(request, 'Import CSV eseguito')
                except Exception as exc:
                    output = (out.getvalue() + '\n' + err.getvalue()).strip()
                    if output:
                        logs.append(output)
                    logs.append(str(exc))
                    messages.error(request, f'Errore import CSV: {exc}')
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        try:
                            os.unlink(tmp_path)
                        except OSError:
                            pass

    return TemplateResponse(
        request,
        'admin/agile/import_tools.html',
        {
            'title': 'Strumenti importazione',
            'ldap_form': ldap_form,
            'csv_form': csv_form,
            'logs': logs,
            'is_superuser': request.user.is_superuser,
            'opts': User._meta,
        },
    )


def _extend_admin_urls(get_urls):
    def wrapped_urls():
        custom_urls = [
            path(
                'agile/import-tools/',
                admin.site.admin_view(import_tools_view),
                name='agile_import_tools',
            ),
        ]
        return custom_urls + get_urls()

    return wrapped_urls


if not getattr(admin.site, '_agile_import_tools_patched', False):
    admin.site.get_urls = _extend_admin_urls(admin.site.get_urls)
    admin.site._agile_import_tools_patched = True


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
            "<code>{{status_label}}</code>, <code>{{status_label_lower}}</code>"
            "<br><strong>Esiti:</strong> "
            "<code>{{change_reason}}</code>, <code>{{rejection_reason}}</code>, <code>{{final_line}}</code>"
            "<br><strong>Referente:</strong> "
            "<code>{{manager_name}}</code>, <code>{{employee_name}}</code>"
            "</div>"
        )

    @staticmethod
    def _sender_from_env() -> str | None:
        from_email = (getattr(settings, 'DEFAULT_FROM_EMAIL', '') or '').strip()
        from_name = (getattr(settings, 'AGILE_EMAIL_FROM_NAME', '') or '').strip()
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
            'status_label': 'APPROVATA',
            'status_label_lower': 'approvata',
            'change_reason': 'Aggiornamento attivita su progetto sperimentale',
            'rejection_reason': 'Motivazione di esempio',
            'final_line': 'La variazione e stata recepita nel piano.',
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
