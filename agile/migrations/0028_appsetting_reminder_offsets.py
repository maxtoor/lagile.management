from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0027_seed_ldap_user_imported_template'),
    ]

    operations = [
        migrations.AddField(
            model_name='appsetting',
            name='manager_monthly_summary_offset_days',
            field=models.SmallIntegerField(
                default=0,
                help_text='Offset in giorni rispetto al primo giorno del mese riepilogato. 0 = primo giorno del mese, 1 = secondo giorno.',
            ),
        ),
        migrations.AddField(
            model_name='appsetting',
            name='submission_reminder_offset_days',
            field=models.SmallIntegerField(
                default=-1,
                help_text='Offset in giorni rispetto al primo giorno del mese da pianificare. -1 = ultimo giorno del mese precedente, 0 = primo giorno del mese.',
            ),
        ),
    ]
