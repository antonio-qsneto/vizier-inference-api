from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.billing import (
    BillingProviderError as IndividualBillingProviderError,
    reconcile_individual_subscription_state,
)
from apps.accounts.models import UserSubscription
from apps.tenants.billing import (
    ClinicBillingProviderError,
    reconcile_clinic_subscription_state,
)
from apps.tenants.models import Clinic


class Command(BaseCommand):
    help = 'Reconcile Stripe subscription state with local DB for clinic and individual billing.'

    def add_arguments(self, parser):
        parser.add_argument('--clinic-id', dest='clinic_id', type=str, default=None)
        parser.add_argument('--limit', dest='limit', type=int, default=0)
        parser.add_argument('--dry-run', dest='dry_run', action='store_true')
        parser.add_argument('--skip-clinic', dest='skip_clinic', action='store_true')
        parser.add_argument('--skip-individual', dest='skip_individual', action='store_true')

    def handle(self, *args, **options):
        clinic_id = options['clinic_id']
        limit = max(0, int(options['limit'] or 0))
        dry_run = bool(options['dry_run'])
        skip_clinic = bool(options['skip_clinic'])
        skip_individual = bool(options['skip_individual'])

        if skip_clinic and skip_individual:
            raise CommandError('At least one scope must be enabled (clinic or individual)')

        clinic_qs = Clinic.objects.exclude(stripe_subscription_id__isnull=True).exclude(
            stripe_subscription_id=''
        )
        if clinic_id:
            clinic_qs = clinic_qs.filter(id=clinic_id)
        clinic_qs = clinic_qs.order_by('id')

        subscription_qs = UserSubscription.objects.exclude(
            stripe_subscription_id__isnull=True
        ).exclude(stripe_subscription_id='').select_related('user').order_by('id')

        if limit:
            clinic_qs = clinic_qs[:limit]
            subscription_qs = subscription_qs[:limit]

        clinics_seen = 0
        clinics_applied = 0
        individuals_seen = 0
        individuals_applied = 0
        failures = 0

        if not skip_clinic:
            for clinic in clinic_qs:
                clinics_seen += 1
                if dry_run:
                    self.stdout.write(f'[DRY-RUN] clinic={clinic.id} subscription={clinic.stripe_subscription_id}')
                    continue

                try:
                    with transaction.atomic():
                        changed = reconcile_clinic_subscription_state(clinic=clinic)
                    if changed:
                        clinics_applied += 1
                except (ClinicBillingProviderError, Exception) as exc:
                    failures += 1
                    self.stderr.write(
                        f'[ERROR] clinic={clinic.id} subscription={clinic.stripe_subscription_id} error={exc}'
                    )

        if not skip_individual:
            for subscription in subscription_qs:
                individuals_seen += 1
                if dry_run:
                    self.stdout.write(
                        f'[DRY-RUN] user={subscription.user_id} '
                        f'subscription={subscription.stripe_subscription_id}'
                    )
                    continue

                try:
                    with transaction.atomic():
                        changed = reconcile_individual_subscription_state(subscription=subscription)
                    if changed:
                        individuals_applied += 1
                except (IndividualBillingProviderError, Exception) as exc:
                    failures += 1
                    self.stderr.write(
                        f'[ERROR] user={subscription.user_id} '
                        f'subscription={subscription.stripe_subscription_id} error={exc}'
                    )

        self.stdout.write(
            'Reconciliation summary: '
            f'clinics_seen={clinics_seen} clinics_applied={clinics_applied} '
            f'individuals_seen={individuals_seen} individuals_applied={individuals_applied} '
            f'failures={failures} dry_run={dry_run}'
        )

