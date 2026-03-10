from django.db import migrations


def backfill_memberships_and_normalize_clinics(apps, schema_editor):
    Clinic = apps.get_model('tenants', 'Clinic')
    Membership = apps.get_model('tenants', 'Membership')
    User = apps.get_model('accounts', 'User')

    paid_legacy_plans = {'starter', 'professional', 'enterprise'}
    valid_plans = {'free', 'clinic_monthly', 'clinic_yearly'}

    for clinic in Clinic.objects.all().iterator():
        updates = []

        if clinic.owner_id:
            Membership.objects.get_or_create(
                account_id=clinic.id,
                user_id=clinic.owner_id,
                defaults={'role': 'admin'},
            )

        clinic_doctor_count = 0
        clinic_users = User.objects.filter(clinic_id=clinic.id, is_active=True).only('id', 'role')
        for user in clinic_users:
            membership_role = 'doctor' if user.role == 'CLINIC_DOCTOR' else 'admin'
            if membership_role == 'doctor':
                clinic_doctor_count += 1

            Membership.objects.get_or_create(
                account_id=clinic.id,
                user_id=user.id,
                defaults={'role': membership_role},
            )

        current_plan = clinic.subscription_plan or 'free'
        if current_plan in paid_legacy_plans:
            clinic.subscription_plan = 'clinic_monthly'
            updates.append('subscription_plan')
        elif current_plan not in valid_plans:
            clinic.subscription_plan = 'free'
            updates.append('subscription_plan')

        if clinic.plan_type != 'clinic':
            clinic.plan_type = 'clinic'
            updates.append('plan_type')

        desired_seat_limit = max(int(clinic.seat_limit or 0), clinic_doctor_count)
        if clinic.seat_limit != desired_seat_limit:
            clinic.seat_limit = desired_seat_limit
            updates.append('seat_limit')

        is_paid_plan = clinic.subscription_plan in {'clinic_monthly', 'clinic_yearly'}
        if is_paid_plan and clinic.account_status == 'canceled':
            clinic.account_status = 'active'
            updates.append('account_status')

        if not is_paid_plan and not clinic.stripe_subscription_id:
            if clinic.account_status != 'canceled':
                clinic.account_status = 'canceled'
                updates.append('account_status')

        if updates:
            clinic.save(update_fields=list(dict.fromkeys(updates)) + ['updated_at'])


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0003_membership_stripewebhookevent_clinic_account_status_and_more'),
    ]

    operations = [
        migrations.RunPython(
            backfill_memberships_and_normalize_clinics,
            noop_reverse,
        ),
    ]
