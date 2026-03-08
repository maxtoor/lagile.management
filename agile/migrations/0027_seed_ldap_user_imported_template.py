from django.db import migrations, models


def seed_template(apps, schema_editor):
    SystemEmailTemplate = apps.get_model('agile', 'SystemEmailTemplate')
    SystemEmailTemplate.objects.get_or_create(
        key='LDAP_USER_IMPORTED',
        defaults={
            'subject_template': 'Nuovo utente LDAP importato: {username}',
            'body_template': (
                'E stato importato automaticamente un nuovo utente al primo login LDAP.\n\n'
                'Username: {username}\n'
                'Nome completo: {full_name}\n'
                'Email: {email}\n'
                'Data import: {import_timestamp}\n\n'
                '{admin_line}'
                'Completare la configurazione nel pannello amministrativo: Attivo, Afferenza territoriale, '
                'Responsabile approvazione, Sottoscrizione AILA e altre impostazioni applicative.'
            ),
        },
    )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0026_alter_departmentpolicy_department_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='systememailtemplate',
            name='key',
            field=models.CharField(
                choices=[
                    ('LDAP_USER_IMPORTED', 'Nuovo utente LDAP importato'),
                    ('CHANGE_REQUEST_SUBMITTED', 'Richiesta variazione inviata'),
                    ('REMINDER_PENDING_SUBMISSION', 'Promemoria invio piano'),
                    ('MANAGER_MONTHLY_SUMMARY', 'Riepilogo mensile referente'),
                    ('PLAN_APPROVED', 'Piano approvato'),
                    ('PLAN_REJECTED', 'Piano rifiutato'),
                    ('CHANGE_APPROVED', 'Variazione approvata'),
                    ('CHANGE_REJECTED', 'Variazione rifiutata'),
                ],
                max_length=40,
                unique=True,
            ),
        ),
        migrations.RunPython(seed_template, noop_reverse),
    ]
