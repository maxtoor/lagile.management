from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0011_backfill_approved_days_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='auto_approve',
            field=models.BooleanField(default=False, verbose_name='Approvazione automatica'),
        ),
    ]
