from django.db import migrations, models


def normalize_manager_summary_setting(apps, schema_editor):
    AppSetting = apps.get_model('agile', 'AppSetting')
    AppSetting.objects.filter(manager_monthly_summary_offset_days__lt=1).update(manager_monthly_summary_offset_days=1)


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0030_update_manager_summary_setting'),
    ]

    operations = [
        migrations.RunPython(normalize_manager_summary_setting, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='appsetting',
            name='manager_monthly_summary_offset_days',
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text='Ultimo giorno del mese, incluso, entro cui il riepilogo puo essere inviato. 1 = solo primo giorno del mese, 3 = dal giorno 1 al giorno 3.',
                verbose_name='Riepilogo referenti: fino al giorno del mese',
            ),
        ),
    ]
