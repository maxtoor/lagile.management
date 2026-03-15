from django.db import migrations, models


def clamp_legacy_submission_offset(apps, schema_editor):
    AppSetting = apps.get_model('agile', 'AppSetting')
    AppSetting.objects.filter(submission_reminder_offset_days__lt=0).update(submission_reminder_offset_days=0)


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0028_appsetting_reminder_offsets'),
    ]

    operations = [
        migrations.RunPython(clamp_legacy_submission_offset, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='appsetting',
            name='submission_reminder_offset_days',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Numero di giorni prima della fine del mese corrente da cui iniziare l'invio. 0 = solo ultimo giorno del mese, 3 = dal terzultimo giorno in poi.",
                verbose_name='Promemoria invio piano: giorni prima della fine mese',
            ),
        ),
        migrations.AlterField(
            model_name='appsetting',
            name='manager_monthly_summary_offset_days',
            field=models.SmallIntegerField(
                default=0,
                help_text='Offset in giorni rispetto al primo giorno del mese riepilogato. 0 = primo giorno del mese, 1 = secondo giorno.',
                verbose_name='Riepilogo referenti: offset dal primo giorno del mese',
            ),
        ),
    ]
