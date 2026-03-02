from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('agile', '0004_remove_absence_worktype'),
    ]

    operations = [
        migrations.AlterField(
            model_name='planday',
            name='notes',
            field=models.TextField(blank=True),
        ),
    ]
