from django.db import migrations


NEW_SUBJECT = 'Promemoria invio piano lavoro agile - {month_name_year}'
NEW_BODY = (
    'Gentile {full_name},\n\n'
    'ti ricordiamo di {submission_action_label} il piano di lavoro agile per {month_name_year}.\n'
    'Stato attuale: {plan_status_label}.\n'
    '{fiduciary_approval_line}\n'
    '{portal_line}'
    'Puoi accedere al portale per completare {submission_completion_label}.'
)


def update_template(apps, schema_editor):
    SystemEmailTemplate = apps.get_model('agile', 'SystemEmailTemplate')
    template = SystemEmailTemplate.objects.filter(key='REMINDER_PENDING_SUBMISSION').first()
    if not template:
        SystemEmailTemplate.objects.create(
            key='REMINDER_PENDING_SUBMISSION',
            subject_template=NEW_SUBJECT,
            body_template=NEW_BODY,
        )
        return

    body = template.body_template or ''
    if '{submission_action_label}' in body:
        return

    template.subject_template = template.subject_template or NEW_SUBJECT
    template.body_template = NEW_BODY
    template.save(update_fields=['subject_template', 'body_template', 'updated_at'])


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):
    dependencies = [
        ('agile', '0035_refresh_ldap_user_imported_template'),
    ]

    operations = [
        migrations.RunPython(update_template, noop_reverse),
    ]
