from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, UserSubscription


@override_settings(
    ENABLE_STRIPE_BILLING=True,
    STRIPE_PRICE_ID_INDIVIDUAL_MONTHLY='price_monthly_test',
    STRIPE_PRICE_ID_INDIVIDUAL_ANNUAL='price_annual_test',
)
class BillingEndpointsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='billing-user@example.com',
            cognito_sub='billing-user-sub',
            role='INDIVIDUAL',
        )
        self.user.set_password('billing-pass-123')
        self.user.save(update_fields=['password', 'updated_at'])
        self.client.force_authenticate(user=self.user)

    def test_plans_endpoint_returns_catalog(self):
        response = self.client.get('/api/auth/billing/plans/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['current_plan'], 'free')
        self.assertEqual(len(response.data['plans']), 2)

    @patch('apps.accounts.billing_views.create_checkout_session')
    def test_checkout_creates_pending_subscription_record(self, create_checkout_session_mock):
        create_checkout_session_mock.return_value = (
            {'id': 'cs_test_123', 'url': 'https://checkout.stripe.test/session'},
            'price_test_123',
        )

        response = self.client.post(
            '/api/auth/billing/checkout/',
            {
                'plan_id': UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
                'success_url': 'http://localhost:3000/billing/success',
                'cancel_url': 'http://localhost:3000/billing/cancel',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('checkout_url', response.data)

        subscription = UserSubscription.objects.get(user=self.user)
        self.assertEqual(subscription.plan, UserSubscription.PLAN_INDIVIDUAL_MONTHLY)
        self.assertEqual(subscription.status, UserSubscription.STATUS_INCOMPLETE)
        self.assertEqual(subscription.stripe_checkout_session_id, 'cs_test_123')
        self.assertEqual(subscription.stripe_price_id, 'price_test_123')

    @patch('apps.accounts.billing_views.create_checkout_session')
    @patch('apps.accounts.billing_views.update_subscription_plan')
    def test_checkout_upgrades_existing_subscription_without_new_checkout(
        self,
        update_subscription_plan_mock,
        create_checkout_session_mock,
    ):
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_ACTIVE,
            stripe_customer_id='cus_test_123',
            stripe_subscription_id='sub_test_123',
            current_period_end=timezone.now() + timedelta(days=30),
        )
        update_subscription_plan_mock.return_value = (
            {
                'id': 'sub_test_123',
                'customer': 'cus_test_123',
                'status': 'active',
                'current_period_end': int((timezone.now() + timedelta(days=365)).timestamp()),
                'items': {
                    'data': [
                        {
                            'price': {
                                'id': 'price_annual_test',
                            }
                        }
                    ]
                },
            },
            'price_annual_test',
        )

        response = self.client.post(
            '/api/auth/billing/checkout/',
            {
                'plan_id': UserSubscription.PLAN_INDIVIDUAL_ANNUAL,
                'success_url': 'http://localhost:3000/billing/success',
                'cancel_url': 'http://localhost:3000/billing/cancel',
                'current_password': 'billing-pass-123',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['mode'], 'subscription_updated')
        create_checkout_session_mock.assert_not_called()
        update_subscription_plan_mock.assert_called_once_with(
            subscription_id='sub_test_123',
            plan_id=UserSubscription.PLAN_INDIVIDUAL_ANNUAL,
        )

        subscription.refresh_from_db()
        self.assertEqual(subscription.plan, UserSubscription.PLAN_INDIVIDUAL_ANNUAL)
        self.assertEqual(subscription.status, UserSubscription.STATUS_ACTIVE)
        self.assertEqual(subscription.stripe_price_id, 'price_annual_test')

    @patch('apps.accounts.billing_views.create_checkout_session')
    @patch('apps.accounts.billing_views.update_subscription_plan')
    def test_checkout_downgrades_existing_subscription_without_new_checkout(
        self,
        update_subscription_plan_mock,
        create_checkout_session_mock,
    ):
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_ANNUAL,
            status=UserSubscription.STATUS_ACTIVE,
            stripe_customer_id='cus_test_123',
            stripe_subscription_id='sub_test_123',
            current_period_end=timezone.now() + timedelta(days=365),
        )
        update_subscription_plan_mock.return_value = (
            {
                'id': 'sub_test_123',
                'customer': 'cus_test_123',
                'status': 'active',
                'current_period_end': int((timezone.now() + timedelta(days=30)).timestamp()),
                'items': {
                    'data': [
                        {
                            'price': {
                                'id': 'price_monthly_test',
                            }
                        }
                    ]
                },
            },
            'price_monthly_test',
        )

        response = self.client.post(
            '/api/auth/billing/checkout/',
            {
                'plan_id': UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
                'success_url': 'http://localhost:3000/billing/success',
                'cancel_url': 'http://localhost:3000/billing/cancel',
                'current_password': 'billing-pass-123',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['mode'], 'subscription_updated')
        create_checkout_session_mock.assert_not_called()
        update_subscription_plan_mock.assert_called_once_with(
            subscription_id='sub_test_123',
            plan_id=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
        )

        subscription.refresh_from_db()
        self.assertEqual(subscription.plan, UserSubscription.PLAN_INDIVIDUAL_MONTHLY)
        self.assertEqual(subscription.status, UserSubscription.STATUS_ACTIVE)
        self.assertEqual(subscription.stripe_price_id, 'price_monthly_test')

    @patch('apps.accounts.billing_views.update_subscription_plan')
    def test_checkout_plan_change_requires_current_password(self, update_subscription_plan_mock):
        UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_ACTIVE,
            stripe_customer_id='cus_test_123',
            stripe_subscription_id='sub_test_123',
            current_period_end=timezone.now() + timedelta(days=30),
        )

        response = self.client.post(
            '/api/auth/billing/checkout/',
            {
                'plan_id': UserSubscription.PLAN_INDIVIDUAL_ANNUAL,
                'success_url': 'http://localhost:3000/billing/success',
                'cancel_url': 'http://localhost:3000/billing/cancel',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('password', str(response.data.get('detail', '')).lower())
        update_subscription_plan_mock.assert_not_called()

    def test_portal_requires_existing_customer(self):
        response = self.client.post('/api/auth/billing/portal/', {}, format='json')
        self.assertEqual(response.status_code, 400)

    @patch('apps.accounts.billing_views.create_customer_portal_session')
    @patch('apps.accounts.billing_views.retrieve_subscription')
    @patch('apps.accounts.billing_views.retrieve_checkout_session')
    def test_portal_recovers_customer_from_checkout_session(
        self,
        retrieve_checkout_session_mock,
        retrieve_subscription_mock,
        create_customer_portal_session_mock,
    ):
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_INCOMPLETE,
            stripe_checkout_session_id='cs_test_123',
        )

        retrieve_checkout_session_mock.return_value = {
            'id': 'cs_test_123',
            'customer': 'cus_recovered_123',
            'subscription': 'sub_recovered_123',
        }
        retrieve_subscription_mock.return_value = {
            'id': 'sub_recovered_123',
            'customer': 'cus_recovered_123',
            'status': 'active',
            'current_period_end': int((timezone.now() + timedelta(days=30)).timestamp()),
            'items': {
                'data': [
                    {
                        'price': {
                            'id': 'price_monthly_test',
                        }
                    }
                ]
            },
        }
        create_customer_portal_session_mock.return_value = {
            'url': 'https://billing.stripe.test/recovered-portal',
        }

        response = self.client.post(
            '/api/auth/billing/portal/',
            {'return_url': 'http://localhost:3000/billing'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['url'], 'https://billing.stripe.test/recovered-portal')

        subscription.refresh_from_db()
        self.assertEqual(subscription.stripe_customer_id, 'cus_recovered_123')
        self.assertEqual(subscription.stripe_subscription_id, 'sub_recovered_123')
        self.assertEqual(subscription.status, UserSubscription.STATUS_ACTIVE)

    @patch('apps.accounts.billing_views.create_customer_portal_session')
    def test_portal_returns_url_for_existing_customer(self, create_customer_portal_session_mock):
        UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_ACTIVE,
            stripe_customer_id='cus_test_123',
            current_period_end=timezone.now() + timedelta(days=30),
        )
        create_customer_portal_session_mock.return_value = {
            'url': 'https://billing.stripe.test/portal-session',
        }

        response = self.client.post(
            '/api/auth/billing/portal/',
            {'return_url': 'http://localhost:3000/billing'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['url'], 'https://billing.stripe.test/portal-session')

    @patch('apps.accounts.billing_views.retrieve_subscription')
    @patch('apps.accounts.billing_views.construct_webhook_event')
    def test_webhook_checkout_completed_activates_subscription(
        self,
        construct_webhook_event_mock,
        retrieve_subscription_mock,
    ):
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_INCOMPLETE,
            stripe_checkout_session_id='cs_test_123',
        )

        construct_webhook_event_mock.return_value = {
            'type': 'checkout.session.completed',
            'data': {
                'object': {
                    'id': 'cs_test_123',
                    'customer': 'cus_test_123',
                    'subscription': 'sub_test_123',
                    'metadata': {
                        'plan_id': UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
                        'user_id': str(self.user.id),
                    },
                }
            },
        }

        future_period_end = int((timezone.now() + timedelta(days=30)).timestamp())
        retrieve_subscription_mock.return_value = {
            'id': 'sub_test_123',
            'customer': 'cus_test_123',
            'status': 'active',
            'current_period_end': future_period_end,
            'items': {
                'data': [
                    {
                        'price': {
                            'id': 'price_monthly_test',
                        }
                    }
                ]
            },
        }

        response = self.client.post(
            '/api/auth/billing/webhook/',
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='test-signature',
        )

        self.assertEqual(response.status_code, 200)

        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.STATUS_ACTIVE)
        self.assertEqual(subscription.stripe_customer_id, 'cus_test_123')
        self.assertEqual(subscription.stripe_subscription_id, 'sub_test_123')
        self.assertTrue(self.user.has_upload_access())

    @patch('apps.accounts.billing_views.construct_webhook_event')
    def test_webhook_subscription_updated_sets_annual_access_window(
        self,
        construct_webhook_event_mock,
    ):
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_ACTIVE,
            stripe_customer_id='cus_test_123',
            stripe_subscription_id='sub_test_123',
        )

        future_period_end = int((timezone.now() + timedelta(days=365)).timestamp())
        construct_webhook_event_mock.return_value = {
            'type': 'customer.subscription.updated',
            'data': {
                'object': {
                    'id': 'sub_test_123',
                    'customer': 'cus_test_123',
                    'status': 'active',
                    'current_period_end': future_period_end,
                    'items': {
                        'data': [
                            {
                                'price': {
                                    'id': 'price_annual_test',
                                }
                            }
                        ]
                    },
                }
            },
        }

        response = self.client.post(
            '/api/auth/billing/webhook/',
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='test-signature',
        )

        self.assertEqual(response.status_code, 200)

        subscription.refresh_from_db()
        self.assertEqual(subscription.plan, UserSubscription.PLAN_INDIVIDUAL_ANNUAL)
        self.assertEqual(subscription.status, UserSubscription.STATUS_ACTIVE)
        self.assertIsNotNone(subscription.current_period_end)
        self.assertGreater(subscription.current_period_end, timezone.now())
        self.assertTrue(self.user.has_upload_access())

    @patch('apps.accounts.billing_views.construct_webhook_event')
    def test_webhook_subscription_deleted_revokes_upload_access(
        self,
        construct_webhook_event_mock,
    ):
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_ACTIVE,
            stripe_customer_id='cus_test_123',
            stripe_subscription_id='sub_test_123',
            current_period_end=timezone.now() + timedelta(days=30),
        )

        past_period_end = int((timezone.now() - timedelta(days=1)).timestamp())
        construct_webhook_event_mock.return_value = {
            'type': 'customer.subscription.deleted',
            'data': {
                'object': {
                    'id': 'sub_test_123',
                    'customer': 'cus_test_123',
                    'status': 'canceled',
                    'current_period_end': past_period_end,
                    'items': {
                        'data': [
                            {
                                'price': {
                                    'id': 'price_monthly_test',
                                }
                            }
                        ]
                    },
                }
            },
        }

        response = self.client.post(
            '/api/auth/billing/webhook/',
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='test-signature',
        )

        self.assertEqual(response.status_code, 200)

        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.STATUS_CANCELED)
        self.assertLessEqual(subscription.current_period_end, timezone.now())

        profile_response = self.client.get('/api/auth/users/me/')
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.data['subscription_plan'], 'free')
        self.assertFalse(self.user.has_upload_access())

    @patch('apps.accounts.billing_views.construct_webhook_event')
    def test_legacy_webhook_url_is_supported(self, construct_webhook_event_mock):
        construct_webhook_event_mock.return_value = {
            'type': 'customer.created',
            'data': {'object': {}},
        }

        response = self.client.post(
            '/api/stripe/webhook/',
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='test-signature',
        )

        self.assertEqual(response.status_code, 200)
