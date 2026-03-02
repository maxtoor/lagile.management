from django.db import migrations, models


def map_processed_to_approved(apps, schema_editor):
    ChangeRequest = apps.get_model('agile', 'ChangeRequest')
    ChangeRequest.objects.filter(status='PROCESSED').update(status='APPROVED')


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0005_planday_notes_textfield'),
    ]

    operations = [
        migrations.AddField(
            model_name='changerequest',
            name='response_reason',
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(map_processed_to_approved, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='changerequest',
            name='status',
            field=models.CharField(
                choices=[('PENDING', 'In attesa'), ('APPROVED', 'Approvata'), ('REJECTED', 'Rifiutata')],
                default='PENDING',
                max_length=20,
            ),
        ),
    ]
