from django.db import migrations


def decouple_staff_from_admin_role(apps, schema_editor):
    User = apps.get_model('agile', 'User')
    User.objects.filter(is_superuser=True).update(role='SUPERADMIN', is_staff=True)
    User.objects.filter(role='SUPERADMIN', is_superuser=False).update(is_staff=True)
    User.objects.filter(role='ADMIN', is_superuser=False).update(is_staff=False)
    User.objects.filter(role='EMPLOYEE', is_superuser=False).update(is_staff=False)


class Migration(migrations.Migration):
    dependencies = [
        ('agile', '0021_seed_manager_monthly_summary_template'),
    ]

    operations = [
        migrations.RunPython(decouple_staff_from_admin_role, migrations.RunPython.noop),
    ]
