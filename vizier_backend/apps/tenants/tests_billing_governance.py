from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User, UserSubscription
from apps.audit.models import AuditLog
from apps.tenants.billing_ledger import (
    mark_event_applied,
    register_clinic_event,
    register_individual_event,
)
from apps.tenants.billing import record_and_process_webhook_event
from apps.tenants.models import Clinic, SubscriptionEventLedger


class SubscriptionEventLedgerTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='ledger-owner@example.com',
            cognito_sub='ledger-owner-sub',
            role='CLINIC_ADMIN',
        )
        self.clinic = Clinic.objects.create(
            name='Ledger Clinic',
            owner=self.owner,
            plan_type=Clinic.PLAN_TYPE_CLINIC,
            account_status=Clinic.ACCOUNT_STATUS_ACTIVE,
            seat_limit=1,
        )

    def test_register_clinic_event_marks_stale_when_older_than_latest_applied(self):
        now = timezone.now()
        latest = register_clinic_event(
            clinic=self.clinic,
            source=SubscriptionEventLedger.SOURCE_WEBHOOK,
            event_type='customer.subscription.updated',
            event_created_at=now,
            idempotency_key='webhook:clinic:evt_latest',
            stripe_event_id='evt_latest',
            stripe_subscription_id='sub_clinic_1',
            payload={'id': 'evt_latest'},
        )
        self.assertTrue(latest.should_apply)
        mark_event_applied(latest.entry)

        stale = register_clinic_event(
            clinic=self.clinic,
            source=SubscriptionEventLedger.SOURCE_WEBHOOK,
            event_type='customer.subscription.deleted',
            event_created_at=now - timedelta(minutes=1),
            idempotency_key='webhook:clinic:evt_old',
            stripe_event_id='evt_old',
            stripe_subscription_id='sub_clinic_1',
            payload={'id': 'evt_old'},
        )

        self.assertFalse(stale.should_apply)
        self.assertEqual(stale.reason, 'stale')
        self.assertIsNotNone(stale.entry)
        stale.entry.refresh_from_db()
        self.assertEqual(stale.entry.status, SubscriptionEventLedger.STATUS_IGNORED_STALE)

    def test_register_individual_event_is_idempotent_by_key(self):
        created_at = timezone.now()
        first = register_individual_event(
            user=self.owner,
            source=SubscriptionEventLedger.SOURCE_WEBHOOK,
            event_type='customer.subscription.updated',
            event_created_at=created_at,
            idempotency_key='webhook:individual:evt_duplicate',
            stripe_event_id='evt_duplicate',
            stripe_subscription_id='sub_individual_1',
            payload={'id': 'evt_duplicate'},
        )
        self.assertTrue(first.should_apply)

        second = register_individual_event(
            user=self.owner,
            source=SubscriptionEventLedger.SOURCE_WEBHOOK,
            event_type='customer.subscription.updated',
            event_created_at=created_at,
            idempotency_key='webhook:individual:evt_duplicate',
            stripe_event_id='evt_duplicate',
            stripe_subscription_id='sub_individual_1',
            payload={'id': 'evt_duplicate'},
        )

        self.assertFalse(second.should_apply)
        self.assertEqual(second.reason, 'duplicate')
        self.assertEqual(
            SubscriptionEventLedger.objects.filter(
                idempotency_key='webhook:individual:evt_duplicate'
            ).count(),
            1,
        )


class BillingGracePolicyModelTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='grace-owner@example.com',
            cognito_sub='grace-owner-sub',
            role='CLINIC_ADMIN',
        )
        self.clinic = Clinic.objects.create(
            name='Grace Clinic',
            owner=self.owner,
            plan_type=Clinic.PLAN_TYPE_CLINIC,
            account_status=Clinic.ACCOUNT_STATUS_PAST_DUE,
            seat_limit=1,
        )

    def test_clinic_can_use_resources_while_past_due_within_grace(self):
        self.clinic.billing_grace_until = timezone.now() + timedelta(days=2)
        self.clinic.save(update_fields=['billing_grace_until', 'updated_at'])
        self.assertTrue(self.clinic.can_use_clinic_resources())

        self.clinic.billing_grace_until = timezone.now() - timedelta(minutes=1)
        self.clinic.save(update_fields=['billing_grace_until', 'updated_at'])
        self.assertFalse(self.clinic.can_use_clinic_resources())

    def test_individual_subscription_has_access_while_past_due_within_grace(self):
        subscription = UserSubscription.objects.create(
            user=self.owner,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_PAST_DUE,
            billing_grace_until=timezone.now() + timedelta(days=2),
        )
        self.assertTrue(subscription.has_active_access())

        subscription.billing_grace_until = timezone.now() - timedelta(minutes=1)
        subscription.save(update_fields=['billing_grace_until', 'updated_at'])
        self.assertFalse(subscription.has_active_access())


class ReconcileStripeBillingCommandTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='reconcile-owner@example.com',
            cognito_sub='reconcile-owner-sub',
            role='CLINIC_ADMIN',
        )
        self.clinic = Clinic.objects.create(
            name='Reconcile Clinic',
            owner=self.owner,
            plan_type=Clinic.PLAN_TYPE_CLINIC,
            account_status=Clinic.ACCOUNT_STATUS_ACTIVE,
            seat_limit=1,
            stripe_subscription_id='sub_clinic_reconcile_1',
        )

        self.individual = User.objects.create_user(
            email='reconcile-individual@example.com',
            cognito_sub='reconcile-individual-sub',
            role='INDIVIDUAL',
        )
        self.individual_subscription = UserSubscription.objects.create(
            user=self.individual,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_ACTIVE,
            stripe_subscription_id='sub_individual_reconcile_1',
        )

    @patch('apps.tenants.management.commands.reconcile_stripe_billing.reconcile_clinic_subscription_state')
    @patch(
        'apps.tenants.management.commands.reconcile_stripe_billing.reconcile_individual_subscription_state'
    )
    def test_reconcile_command_dry_run_does_not_apply(
        self,
        reconcile_individual_subscription_state_mock,
        reconcile_clinic_subscription_state_mock,
    ):
        out = StringIO()

        call_command('reconcile_stripe_billing', '--dry-run', stdout=out)

        self.assertFalse(reconcile_clinic_subscription_state_mock.called)
        self.assertFalse(reconcile_individual_subscription_state_mock.called)

        output = out.getvalue()
        self.assertIn(f'[DRY-RUN] clinic={self.clinic.id}', output)
        self.assertIn(f'[DRY-RUN] user={self.individual.id}', output)
        self.assertIn('dry_run=True', output)

    @patch('apps.tenants.management.commands.reconcile_stripe_billing.reconcile_clinic_subscription_state')
    @patch(
        'apps.tenants.management.commands.reconcile_stripe_billing.reconcile_individual_subscription_state'
    )
    def test_reconcile_command_applies_and_reports_summary(
        self,
        reconcile_individual_subscription_state_mock,
        reconcile_clinic_subscription_state_mock,
    ):
        reconcile_clinic_subscription_state_mock.return_value = True
        reconcile_individual_subscription_state_mock.return_value = True
        out = StringIO()

        call_command('reconcile_stripe_billing', stdout=out)

        reconcile_clinic_subscription_state_mock.assert_called_once_with(clinic=self.clinic)
        reconcile_individual_subscription_state_mock.assert_called_once_with(
            subscription=self.individual_subscription
        )

        output = out.getvalue()
        self.assertIn('clinics_applied=1', output)
        self.assertIn('individuals_applied=1', output)
        self.assertIn('failures=0', output)


class BillingWebhookAuditOutcomeTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email='webhook-audit-owner@example.com',
            cognito_sub='webhook-audit-owner-sub',
            role='CLINIC_ADMIN',
        )
        self.clinic = Clinic.objects.create(
            name='Webhook Audit Clinic',
            owner=self.owner,
            plan_type=Clinic.PLAN_TYPE_CLINIC,
            account_status=Clinic.ACCOUNT_STATUS_ACTIVE,
            seat_limit=1,
            stripe_subscription_id='sub_webhook_audit_1',
            stripe_customer_id='cus_webhook_audit_1',
        )

    @patch('apps.tenants.billing.process_stripe_event')
    def test_webhook_out_of_order_event_creates_ignored_audit(self, process_stripe_event_mock):
        process_stripe_event_mock.return_value = None

        first = {
            'id': 'evt_webhook_new_1',
            'type': 'customer.subscription.updated',
            'created': 200,
            'livemode': False,
            'data': {'object': {'id': self.clinic.stripe_subscription_id}},
        }
        old = {
            'id': 'evt_webhook_old_1',
            'type': 'customer.subscription.updated',
            'created': 100,
            'livemode': False,
            'data': {'object': {'id': self.clinic.stripe_subscription_id}},
        }

        self.assertTrue(record_and_process_webhook_event(first))
        self.assertTrue(record_and_process_webhook_event(old))

        self.assertTrue(
            AuditLog.objects.filter(
                clinic=self.clinic,
                action='BILLING_WEBHOOK_PROCESSED',
                resource_id='evt_webhook_new_1',
            ).exists()
        )
        ignored = AuditLog.objects.filter(
            clinic=self.clinic,
            action='BILLING_WEBHOOK_IGNORED',
            resource_id='evt_webhook_old_1',
        ).first()
        self.assertIsNotNone(ignored)
        self.assertEqual((ignored.details or {}).get('reason'), 'stale')

    @patch('apps.tenants.billing.process_stripe_event')
    def test_duplicate_event_id_creates_ignored_audit(self, process_stripe_event_mock):
        process_stripe_event_mock.return_value = None
        payload = {
            'id': 'evt_webhook_duplicate_1',
            'type': 'customer.subscription.updated',
            'created': 250,
            'livemode': False,
            'data': {'object': {'id': self.clinic.stripe_subscription_id}},
        }

        self.assertTrue(record_and_process_webhook_event(payload))
        self.assertFalse(record_and_process_webhook_event(payload))

        ignored = AuditLog.objects.filter(
            clinic=self.clinic,
            action='BILLING_WEBHOOK_IGNORED',
            resource_id='evt_webhook_duplicate_1',
        ).order_by('-timestamp').first()
        self.assertIsNotNone(ignored)
        self.assertEqual((ignored.details or {}).get('reason'), 'duplicate_event_id')
