from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('agile', '0013_user_aila_subscribed'),
    ]

    operations = [
        migrations.CreateModel(
            name='SystemEmailTemplate',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(choices=[('PLAN_APPROVED', 'Piano approvato'), ('PLAN_REJECTED', 'Piano rifiutato'), ('CHANGE_APPROVED', 'Variazione approvata'), ('CHANGE_REJECTED', 'Variazione rifiutata')], max_length=40, unique=True)),
                ('subject_template', models.CharField(max_length=255)),
                ('body_template', models.TextField(help_text='Template con segnaposto Python-style, es: {first_name}, {username}, {month_label}, {status_label}, {rejection_reason}, {change_reason}')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Template email di sistema',
                'verbose_name_plural': 'Template email di sistema',
                'ordering': ('key',),
            },
        ),
    ]
