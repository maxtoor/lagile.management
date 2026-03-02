from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('agile', '0003_changerequest'),
    ]

    operations = [
        migrations.AlterField(
            model_name='planday',
            name='work_type',
            field=models.CharField(choices=[('ON_SITE', 'In sede'), ('REMOTE', 'Lavoro agile')], max_length=20),
        ),
    ]
