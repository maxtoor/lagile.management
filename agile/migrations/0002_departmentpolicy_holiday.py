from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('agile', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DepartmentPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('department', models.CharField(max_length=120, unique=True)),
                ('max_remote_days', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('february_max_remote_days', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('require_on_site_prevalence', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ('department',),
            },
        ),
        migrations.CreateModel(
            name='Holiday',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day', models.DateField()),
                ('name', models.CharField(max_length=120)),
                ('department', models.CharField(blank=True, help_text='Vuoto = festivita valida per tutti i reparti', max_length=120)),
            ],
            options={
                'ordering': ('day', 'department'),
                'unique_together': {('day', 'department')},
            },
        ),
    ]
