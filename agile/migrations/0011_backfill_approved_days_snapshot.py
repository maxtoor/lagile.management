from django.db import migrations


def backfill_approved_snapshot(apps, schema_editor):
    MonthlyPlan = apps.get_model('agile', 'MonthlyPlan')
    PlanDay = apps.get_model('agile', 'PlanDay')

    plans = MonthlyPlan.objects.filter(status='APPROVED')
    for plan in plans.iterator():
        if plan.approved_days_snapshot:
            continue
        days = (
            PlanDay.objects.filter(plan_id=plan.id)
            .order_by('day')
            .values('day', 'work_type', 'notes')
        )
        snapshot = [
            {
                'day': row['day'].isoformat(),
                'work_type': row['work_type'],
                'notes': row['notes'] or '',
            }
            for row in days
        ]
        if snapshot:
            plan.approved_days_snapshot = snapshot
            plan.save(update_fields=['approved_days_snapshot'])


def reverse_noop(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('agile', '0010_monthlyplan_approved_days_snapshot'),
    ]

    operations = [
        migrations.RunPython(backfill_approved_snapshot, reverse_noop),
    ]
