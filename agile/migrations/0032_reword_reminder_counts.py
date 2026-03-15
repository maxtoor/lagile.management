from django.db import migrations, models


def normalize_reminder_counts(apps, schema_editor):
    AppSetting = apps.get_model('agile', 'AppSetting')
    AppSetting.objects.filter(submission_reminder_offset_days__lt=1).update(submission_reminder_offset_days=1)
    AppSetting.objects.filter(manager_monthly_summary_offset_days__lt=1).update(manager_monthly_summary_offset_days=1)


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0031_reword_manager_summary_setting'),
    ]

    operations = [
        migrations.RunPython(normalize_reminder_counts, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='appsetting',
            name='manager_monthly_summary_offset_days',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Numero di invii giornalieri possibili dopo la scadenza di fine mese. 1 = solo primo giorno del mese, 2 = primo e secondo giorno, 3 = primi tre giorni.',
                verbose_name='Riepilogo referenti: quante volte inviare dopo la scadenza',
            ),
        ),
        migrations.AlterField(
            model_name='appsetting',
            name='submission_reminder_offset_days',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Numero di invii giornalieri possibili prima della scadenza di fine mese. 1 = solo ultimo giorno del mese, 2 = penultimo e ultimo giorno, 3 = ultimi tre giorni.',
                verbose_name='Promemoria utenti: quante volte inviare prima della scadenza',
            ),
        ),
    ]
