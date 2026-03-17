from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0033_appsetting_favicon_public_url'),
    ]

    operations = [
        migrations.AlterField(
            model_name='departmentpolicy',
            name='department',
            field=models.CharField(
                choices=[('Napoli', 'Napoli'), ('Catania', 'Catania'), ('Sassari', 'Sassari'), ('Padova', 'Padova')],
                help_text='Es. Napoli, Catania, Sassari, Padova, ecc.',
                max_length=120,
                unique=True,
                verbose_name='Afferenza territoriale',
            ),
        ),
        migrations.AlterField(
            model_name='holiday',
            name='department',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'Tutte le afferenze territoriali'),
                    ('Napoli', 'Napoli'),
                    ('Catania', 'Catania'),
                    ('Sassari', 'Sassari'),
                    ('Padova', 'Padova'),
                ],
                help_text='Vuoto = festivita valida per tutte le afferenze territoriali',
                max_length=120,
                verbose_name='Afferenza territoriale',
            ),
        ),
        migrations.AlterField(
            model_name='systememailtemplate',
            name='body_template',
            field=models.TextField(
                help_text='Template con segnaposto Python-style, es: {first_name}, {username}, {month_label}, {status_label}, {rejection_reason}, {change_reason}, {portal_url}, {admin_url}',
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='department',
            field=models.CharField(
                blank=True,
                choices=[('Napoli', 'Napoli'), ('Catania', 'Catania'), ('Sassari', 'Sassari'), ('Padova', 'Padova')],
                help_text='Impostare la sede di servizio',
                max_length=120,
                verbose_name='Afferenza territoriale',
            ),
        ),
    ]
