from django.db import migrations, models


def clamp_legacy_manager_offset(apps, schema_editor):
    AppSetting = apps.get_model('agile', 'AppSetting')
    AppSetting.objects.filter(manager_monthly_summary_offset_days__lt=0).update(manager_monthly_summary_offset_days=0)


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0029_update_submission_reminder_setting'),
    ]

    operations = [
        migrations.RunPython(clamp_legacy_manager_offset, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='appsetting',
            name='manager_monthly_summary_offset_days',
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text='Numero di giorni, a partire dal primo del mese, in cui il riepilogo puo essere inviato. 0 = solo primo giorno del mese, 3 = dal giorno 1 al giorno 4.',
                verbose_name='Riepilogo referenti: giorni dal primo del mese',
            ),
        ),
    ]
