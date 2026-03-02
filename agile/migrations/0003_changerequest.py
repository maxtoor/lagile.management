from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('agile', '0002_departmentpolicy_holiday'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChangeRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reason', models.TextField()),
                ('status', models.CharField(choices=[('PENDING', 'In attesa'), ('PROCESSED', 'Gestita')], default='PENDING', max_length=20)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('plan', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='change_requests', to='agile.monthlyplan')),
                ('processed_by', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='processed_change_requests', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='change_requests', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at',),
            },
        ),
    ]
