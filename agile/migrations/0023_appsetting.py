from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0022_decouple_staff_from_admin_role'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_display_format', models.CharField(blank=True, choices=[('IT', 'Italiano (gg/mm/aaaa)'), ('ISO', 'ISO (aaaa-mm-gg)')], help_text='Se vuoto usa AGILE_DATE_DISPLAY_FORMAT da .env', max_length=8)),
                ('login_logo_url', models.URLField(blank=True, help_text='Se vuoto usa AGILE_LOGIN_LOGO_URL da .env')),
                ('company_name', models.CharField(blank=True, help_text='Se vuoto usa AGILE_COMPANY_NAME da .env', max_length=120)),
                ('copyright_year', models.PositiveIntegerField(blank=True, help_text='Se vuoto usa AGILE_COPYRIGHT_YEAR da .env', null=True)),
                ('default_from_email', models.EmailField(blank=True, help_text='Se vuoto usa DEFAULT_FROM_EMAIL da .env', max_length=254)),
                ('email_from_name', models.CharField(blank=True, help_text='Se vuoto usa AGILE_EMAIL_FROM_NAME da .env', max_length=120)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Impostazioni applicazione',
                'verbose_name_plural': 'Impostazioni applicazione',
            },
        ),
    ]
