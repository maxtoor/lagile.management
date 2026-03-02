from django.db import migrations


def seed_template(apps, schema_editor):
    SystemEmailTemplate = apps.get_model('agile', 'SystemEmailTemplate')
    SystemEmailTemplate.objects.get_or_create(
        key='REMINDER_PENDING_SUBMISSION',
        defaults={
            'subject_template': 'Promemoria invio piano lavoro agile - {month_name_year}',
            'body_template': (
                'Gentile {full_name},\n\n'
                'ti ricordiamo di inviare in approvazione il piano di lavoro agile per {month_name_year}.\n'
                'Stato attuale: {plan_status_label}.\n\n'
                "Puoi accedere al portale per completare l'invio."
            ),
        },
    )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ('agile', '0019_replace_month_label_placeholder'),
    ]

    operations = [
        migrations.RunPython(seed_template, noop_reverse),
    ]
