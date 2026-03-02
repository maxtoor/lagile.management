from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0008_site_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='manager',
            field=models.ForeignKey(
                blank=True,
                limit_choices_to=Q(role__in=['ADMIN', 'SUPERADMIN']) | Q(is_superuser=True),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='employees',
                to='agile.user',
                verbose_name='Amministratore referente',
            ),
        ),
    ]
