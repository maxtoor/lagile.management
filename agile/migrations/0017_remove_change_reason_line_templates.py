from django.db import migrations


def update_change_templates(apps, schema_editor):
    SystemEmailTemplate = apps.get_model('agile', 'SystemEmailTemplate')
    body = (
        'Gentile {full_name},\n'
        'La tua richiesta variazione per {month_name_year} e stata {status_label_lower}.\n'
        '{final_line}\n'
        '\n'
        'Puoi accedere al portale per vedere il dettaglio.'
    )
    for key in ('CHANGE_APPROVED', 'CHANGE_REJECTED'):
        obj = SystemEmailTemplate.objects.filter(key=key).first()
        if not obj:
            continue
        obj.body_template = body
        obj.save(update_fields=['body_template', 'updated_at'])


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ('agile', '0016_update_change_email_templates'),
    ]

    operations = [
        migrations.RunPython(update_change_templates, noop_reverse),
    ]
