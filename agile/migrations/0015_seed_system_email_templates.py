from django.db import migrations


def seed_templates(apps, schema_editor):
    SystemEmailTemplate = apps.get_model('agile', 'SystemEmailTemplate')

    defaults = {
        'PLAN_APPROVED': {
            'subject_template': 'Esito piano lavoro agile {month_label}: {status_label}',
            'body_template': (
                'Ciao {first_name_or_username},\n\n'
                'Il tuo piano di lavoro agile per {month_label} e stato {status_label_lower}.\n'
                '{final_line}\n\n'
                'Puoi accedere al portale per vedere il dettaglio.'
            ),
        },
        'PLAN_REJECTED': {
            'subject_template': 'Esito piano lavoro agile {month_label}: {status_label}',
            'body_template': (
                'Ciao {first_name_or_username},\n\n'
                'Il tuo piano di lavoro agile per {month_label} e stato {status_label_lower}.\n'
                '{final_line}\n\n'
                'Puoi accedere al portale per vedere il dettaglio.'
            ),
        },
        'CHANGE_APPROVED': {
            'subject_template': 'Esito richiesta variazione {month_label}: {status_label}',
            'body_template': (
                'Ciao {first_name_or_username},\n\n'
                'La tua richiesta variazione per {month_label} e stata {status_label_lower}.\n'
                'Motivazione richiesta: {change_reason}\n'
                '{final_line}\n\n'
                'Puoi accedere al portale per vedere il dettaglio.'
            ),
        },
        'CHANGE_REJECTED': {
            'subject_template': 'Esito richiesta variazione {month_label}: {status_label}',
            'body_template': (
                'Ciao {first_name_or_username},\n\n'
                'La tua richiesta variazione per {month_label} e stata {status_label_lower}.\n'
                'Motivazione richiesta: {change_reason}\n'
                '{final_line}\n\n'
                'Puoi accedere al portale per vedere il dettaglio.'
            ),
        },
    }

    for key, payload in defaults.items():
        SystemEmailTemplate.objects.get_or_create(
            key=key,
            defaults=payload,
        )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ('agile', '0014_systememailtemplate'),
    ]

    operations = [
        migrations.RunPython(seed_templates, noop_reverse),
    ]
