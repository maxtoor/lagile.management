from django.db import migrations


def refresh_ldap_user_imported_template(apps, schema_editor):
    SystemEmailTemplate = apps.get_model('agile', 'SystemEmailTemplate')
    template = SystemEmailTemplate.objects.filter(key='LDAP_USER_IMPORTED').first()
    if not template:
        return

    body = template.body_template or ''
    if '{admin_line}' not in body and 'Afferenza territoriale' not in body:
        return

    template.subject_template = 'Nuovo utente LDAP importato: {username}'
    template.body_template = (
        'E stato importato automaticamente un nuovo utente al primo login LDAP.\n\n'
        'Username: {username}\n'
        'Nome completo: {full_name}\n'
        'Email: {email}\n'
        'Data import: {import_timestamp}\n\n'
        'Pannello amministrativo: {admin_url}\n'
        'Portale applicazione: {portal_url}\n\n'
        'Completare la configurazione nel pannello amministrativo: Attivo, Sede operativa, '
        'Responsabile approvazione, Sottoscrizione AILA e altre impostazioni applicative.'
    )
    template.save(update_fields=['subject_template', 'body_template'])


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0034_alter_departmentpolicy_department_and_more'),
    ]

    operations = [
        migrations.RunPython(refresh_ldap_user_imported_template, migrations.RunPython.noop),
    ]
