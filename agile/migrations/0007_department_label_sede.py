from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0006_changerequest_review_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='department',
            field=models.CharField(blank=True, max_length=120, verbose_name='Sede'),
        ),
        migrations.AlterField(
            model_name='departmentpolicy',
            name='department',
            field=models.CharField(max_length=120, unique=True, verbose_name='Sede'),
        ),
        migrations.AlterField(
            model_name='holiday',
            name='department',
            field=models.CharField(
                blank=True,
                help_text='Vuoto = festivita valida per tutte le sedi',
                max_length=120,
                verbose_name='Sede',
            ),
        ),
    ]
