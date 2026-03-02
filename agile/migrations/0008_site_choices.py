from django.db import migrations, models


SITE_CHOICES = (
    ('Napoli', 'Napoli'),
    ('Catania', 'Catania'),
    ('Sassari', 'Sassari'),
    ('Padova', 'Padova'),
)

HOLIDAY_SITE_CHOICES = (('', 'Tutte le sedi'),) + SITE_CHOICES


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0007_department_label_sede'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='department',
            field=models.CharField(blank=True, choices=SITE_CHOICES, max_length=120, verbose_name='Sede'),
        ),
        migrations.AlterField(
            model_name='departmentpolicy',
            name='department',
            field=models.CharField(choices=SITE_CHOICES, max_length=120, unique=True, verbose_name='Sede'),
        ),
        migrations.AlterField(
            model_name='holiday',
            name='department',
            field=models.CharField(
                blank=True,
                choices=HOLIDAY_SITE_CHOICES,
                help_text='Vuoto = festivita valida per tutte le sedi',
                max_length=120,
                verbose_name='Sede',
            ),
        ),
    ]
