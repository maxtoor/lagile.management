from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0024_agilegroup_alter_systememailtemplate_key_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='onboarding_pending',
            field=models.BooleanField(default=False, verbose_name='Onboarding in attesa'),
        ),
    ]
