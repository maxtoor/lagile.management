from django.conf import settings
from django.contrib.auth.models import UserManager
from django.db import migrations, models
import django.contrib.auth.validators
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('username', models.CharField(error_messages={'unique': 'A user with that username already exists.'}, help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.', max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name='username')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name='email address')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('role', models.CharField(choices=[('EMPLOYEE', 'Dipendente'), ('ADMIN', 'Amministratore'), ('SUPERADMIN', 'Super Admin')], default='EMPLOYEE', max_length=20)),
                ('department', models.CharField(blank=True, max_length=120)),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.permission', verbose_name='user permissions')),
            ],
            options={
                'verbose_name': 'user',
                'verbose_name_plural': 'users',
                'abstract': False,
            },
            managers=[
                ('objects', UserManager()),
            ],
        ),
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(max_length=60)),
                ('target_type', models.CharField(max_length=60)),
                ('target_id', models.PositiveIntegerField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at',),
            },
        ),
        migrations.CreateModel(
            name='MonthlyPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.PositiveIntegerField()),
                ('month', models.PositiveSmallIntegerField()),
                ('status', models.CharField(choices=[('DRAFT', 'Bozza'), ('SUBMITTED', 'Inviato'), ('APPROVED', 'Approvato'), ('REJECTED', 'Rifiutato')], default='DRAFT', max_length=20)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('rejection_reason', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='approved_plans', to=settings.AUTH_USER_MODEL)),
                ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='monthly_plans', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-year', '-month', 'user__username'),
                'unique_together': {('user', 'year', 'month')},
            },
        ),
        migrations.CreateModel(
            name='PlanDay',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day', models.DateField()),
                ('work_type', models.CharField(choices=[('ON_SITE', 'In sede'), ('REMOTE', 'Lavoro agile'), ('ABSENCE', 'Assenza')], max_length=20)),
                ('notes', models.CharField(blank=True, max_length=255)),
                ('plan', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='days', to='agile.monthlyplan')),
            ],
            options={
                'ordering': ('day',),
                'unique_together': {('plan', 'day')},
            },
        ),
    ]
