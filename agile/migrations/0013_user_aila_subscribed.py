from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('agile', '0012_user_auto_approve'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='aila_subscribed',
            field=models.BooleanField(default=False, verbose_name='Sottoscrizione AILA'),
        ),
    ]
