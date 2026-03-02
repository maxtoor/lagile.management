from django.db import migrations


def seed_template(apps, schema_editor):
    SystemEmailTemplate = apps.get_model('agile', 'SystemEmailTemplate')
    SystemEmailTemplate.objects.get_or_create(
        key='MANAGER_MONTHLY_SUMMARY',
        defaults={
            'subject_template': 'Riepilogo richieste e piani - {month_name_year}',
            'body_template': (
                'Gentile {manager_name},\n\n'
                'Riepilogo per {month_name_year}.\n\n'
                'Piani in attesa di approvazione ({pending_count}):\n'
                '{pending_lines}\n\n'
                'Utenti senza piano del mese ({missing_count}):\n'
                '{missing_lines}\n\n'
                'Puoi accedere al portale per gestire le richieste.'
            ),
        },
    )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ('agile', '0020_seed_submission_reminder_template'),
    ]

    operations = [
        migrations.RunPython(seed_template, noop_reverse),
    ]
