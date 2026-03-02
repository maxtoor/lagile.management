from django.db import migrations


def replace_placeholder(apps, schema_editor):
    SystemEmailTemplate = apps.get_model('agile', 'SystemEmailTemplate')
    for item in SystemEmailTemplate.objects.all():
        subject = (item.subject_template or '').replace('{month_label}', '{month_name_year}')
        body = (item.body_template or '').replace('{month_label}', '{month_name_year}')
        updates = []
        if subject != item.subject_template:
            item.subject_template = subject
            updates.append('subject_template')
        if body != item.body_template:
            item.body_template = body
            updates.append('body_template')
        if updates:
            updates.append('updated_at')
            item.save(update_fields=updates)


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ('agile', '0018_seed_change_request_submitted_template'),
    ]

    operations = [
        migrations.RunPython(replace_placeholder, noop_reverse),
    ]
