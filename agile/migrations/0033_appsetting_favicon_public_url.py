from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0032_reword_reminder_counts'),
    ]

    operations = [
        migrations.AddField(
            model_name='appsetting',
            name='favicon_url',
            field=models.URLField(
                blank=True,
                help_text='Se vuoto usa AGILE_FAVICON_URL da .env o la favicon statica di default',
            ),
        ),
        migrations.AddField(
            model_name='appsetting',
            name='public_base_url',
            field=models.URLField(
                blank=True,
                help_text='Se vuoto usa AGILE_PUBLIC_BASE_URL da .env',
            ),
        ),
    ]
