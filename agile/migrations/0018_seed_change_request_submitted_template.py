from django.db import migrations


def seed_template(apps, schema_editor):
    SystemEmailTemplate = apps.get_model('agile', 'SystemEmailTemplate')
    SystemEmailTemplate.objects.get_or_create(
        key='CHANGE_REQUEST_SUBMITTED',
        defaults={
            'subject_template': 'Nuova richiesta variazione da approvare - {month_label}',
            'body_template': (
                'Gentile {manager_name},\n\n'
                "L'utente {employee_name} ha inviato una richiesta variazione per il mese {month_label}.\n"
                'Motivazione richiesta: {change_reason}\n\n'
                'Puoi accedere al portale per approvare o rifiutare la richiesta.'
            ),
        },
    )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ('agile', '0017_remove_change_reason_line_templates'),
    ]

    operations = [
        migrations.RunPython(seed_template, noop_reverse),
    ]
