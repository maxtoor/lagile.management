from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0009_user_manager'),
    ]

    operations = [
        migrations.AddField(
            model_name='monthlyplan',
            name='approved_days_snapshot',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
