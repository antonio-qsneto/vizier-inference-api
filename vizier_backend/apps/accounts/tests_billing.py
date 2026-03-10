from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, UserSubscription
from apps.tenants.models import Clinic, Membership, SubscriptionEventLedger


@override_settings(
    ENABLE_STRIPE_BILLING=True,
    STRIPE_PRICE_ID_INDIVIDUAL_MONTHLY='price_monthly_test',
    STRIPE_PRICE_ID_INDIVIDUAL_ANNUAL='price_annual_test',
    STRIPE_ALLOWED_REDIRECT_ORIGINS=[
        'http://localhost:3000',
        'http://127.0.0.1:3000',
    ],
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
    def test_checkout_rejects_disallowed_redirect_urls(self, create_checkout_session_mock):
        response = self.client.post(
            '/api/auth/billing/checkout/',
            {
                'plan_id': UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
                'success_url': 'https://evil.example.com/success',
                'cancel_url': 'https://evil.example.com/cancel',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('success_url', response.data['detail'])
        create_checkout_session_mock.assert_not_called()

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

    @patch('apps.accounts.billing_views.create_customer_portal_session')
    def test_portal_rejects_disallowed_return_url(self, create_customer_portal_session_mock):
        UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_ACTIVE,
            stripe_customer_id='cus_test_123',
            current_period_end=timezone.now() + timedelta(days=30),
        )

        response = self.client.post(
            '/api/auth/billing/portal/',
            {'return_url': 'https://evil.example.com/portal'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('return_url', response.data['detail'])
        create_customer_portal_session_mock.assert_not_called()

    @patch('apps.accounts.billing_views.retrieve_subscription')
    @patch('apps.accounts.billing_views.retrieve_checkout_session')
    def test_sync_updates_subscription_after_checkout_return(
        self,
        retrieve_checkout_session_mock,
        retrieve_subscription_mock,
    ):
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_INCOMPLETE,
            stripe_checkout_session_id='cs_test_sync_123',
        )
        retrieve_checkout_session_mock.return_value = {
            'id': 'cs_test_sync_123',
            'customer': 'cus_sync_123',
            'subscription': 'sub_sync_123',
            'client_reference_id': str(self.user.id),
            'metadata': {
                'user_id': str(self.user.id),
                'plan_id': UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            },
        }
        retrieve_subscription_mock.return_value = {
            'id': 'sub_sync_123',
            'customer': 'cus_sync_123',
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

        response = self.client.post(
            '/api/auth/billing/sync/',
            {'checkout_session_id': 'cs_test_sync_123'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['plan'], UserSubscription.PLAN_INDIVIDUAL_MONTHLY)
        self.assertEqual(response.data['status'], UserSubscription.STATUS_ACTIVE)

        subscription.refresh_from_db()
        self.assertEqual(subscription.stripe_customer_id, 'cus_sync_123')
        self.assertEqual(subscription.stripe_subscription_id, 'sub_sync_123')
        self.assertEqual(subscription.status, UserSubscription.STATUS_ACTIVE)

    @patch('apps.accounts.billing_views.retrieve_checkout_session')
    def test_sync_returns_409_while_checkout_is_pending(self, retrieve_checkout_session_mock):
        UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_INCOMPLETE,
            stripe_checkout_session_id='cs_test_pending_123',
        )
        retrieve_checkout_session_mock.return_value = {
            'id': 'cs_test_pending_123',
            'customer': 'cus_pending_123',
            'subscription': None,
            'client_reference_id': str(self.user.id),
            'metadata': {
                'user_id': str(self.user.id),
                'plan_id': UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            },
        }

        response = self.client.post(
            '/api/auth/billing/sync/',
            {'checkout_session_id': 'cs_test_pending_123'},
            format='json',
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn('Try again', response.data['detail'])

    def test_cancel_requires_existing_stripe_subscription(self):
        response = self.client.post('/api/auth/billing/cancel/', {}, format='json')
        self.assertEqual(response.status_code, 409)

    @patch('apps.accounts.billing_views.cancel_subscription_at_period_end')
    def test_cancel_marks_local_state_as_canceled_until_period_end(
        self,
        cancel_subscription_at_period_end_mock,
    ):
        period_end = int((timezone.now() + timedelta(days=20)).timestamp())
        subscription = UserSubscription.objects.create(
            user=self.user,
            plan=UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            status=UserSubscription.STATUS_ACTIVE,
            stripe_customer_id='cus_cancel_test',
            stripe_subscription_id='sub_cancel_test',
            current_period_end=timezone.now() + timedelta(days=20),
        )
        cancel_subscription_at_period_end_mock.return_value = {
            'id': 'sub_cancel_test',
            'customer': 'cus_cancel_test',
            'status': 'active',
            'cancel_at_period_end': True,
            'current_period_end': period_end,
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

        response = self.client.post('/api/auth/billing/cancel/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], UserSubscription.STATUS_CANCELED)
        self.assertTrue(response.data['cancel_at_period_end'])

        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.STATUS_CANCELED)
        self.assertTrue(subscription.cancel_at_period_end)
        self.assertIsNotNone(subscription.canceled_at)
        self.assertTrue(subscription.has_active_access())

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
    def test_webhook_subscription_past_due_sets_grace_window(
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

        with self.settings(BILLING_DUNNING_GRACE_DAYS=3):
            construct_webhook_event_mock.return_value = {
                'id': 'evt_individual_past_due_1',
                'type': 'customer.subscription.updated',
                'created': int(timezone.now().timestamp()),
                'data': {
                    'object': {
                        'id': 'sub_test_123',
                        'customer': 'cus_test_123',
                        'status': 'past_due',
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
        self.assertEqual(subscription.status, UserSubscription.STATUS_PAST_DUE)
        self.assertIsNotNone(subscription.billing_grace_until)
        self.assertGreater(subscription.billing_grace_until, timezone.now())
        self.assertTrue(self.user.has_upload_access())

        subscription.billing_grace_until = timezone.now() - timedelta(minutes=1)
        subscription.save(update_fields=['billing_grace_until', 'updated_at'])
        self.assertFalse(self.user.has_upload_access())

    @patch('apps.accounts.billing_views.construct_webhook_event')
    def test_webhook_ignores_stale_subscription_event(
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

        construct_webhook_event_mock.side_effect = [
            {
                'id': 'evt_individual_new_1',
                'type': 'customer.subscription.updated',
                'created': 200,
                'data': {
                    'object': {
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
                    }
                },
            },
            {
                'id': 'evt_individual_old_1',
                'type': 'customer.subscription.deleted',
                'created': 100,
                'data': {
                    'object': {
                        'id': 'sub_test_123',
                        'customer': 'cus_test_123',
                        'status': 'canceled',
                        'current_period_end': int((timezone.now() - timedelta(days=1)).timestamp()),
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
            },
        ]

        first = self.client.post(
            '/api/auth/billing/webhook/',
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='test-signature',
        )
        second = self.client.post(
            '/api/auth/billing/webhook/',
            data=b'{}',
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE='test-signature',
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        subscription.refresh_from_db()
        self.assertEqual(subscription.status, UserSubscription.STATUS_ACTIVE)
        self.assertEqual(subscription.plan, UserSubscription.PLAN_INDIVIDUAL_ANNUAL)

        stale_entry = SubscriptionEventLedger.objects.get(
            idempotency_key='webhook:individual:evt_individual_old_1'
        )
        self.assertEqual(
            stale_entry.status,
            SubscriptionEventLedger.STATUS_IGNORED_STALE,
        )

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


@override_settings(
    ENABLE_STRIPE_BILLING=True,
    STRIPE_ALLOWED_REDIRECT_ORIGINS=[
        'http://localhost:3000',
        'http://127.0.0.1:3000',
    ],
)
class ClinicLinkedUserBillingRestrictionsTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email='clinic-admin-billing@example.com',
            cognito_sub='clinic-admin-billing-sub',
            role='CLINIC_ADMIN',
        )
        self.clinic = Clinic.objects.create(
            name='Billing Restriction Clinic',
            owner=self.admin,
            account_status=Clinic.ACCOUNT_STATUS_ACTIVE,
            plan_type=Clinic.PLAN_TYPE_CLINIC,
            seat_limit=2,
        )
        self.admin.clinic = self.clinic
        self.admin.save(update_fields=['clinic', 'updated_at'])
        Membership.objects.create(
            account=self.clinic,
            user=self.admin,
            role=Membership.ROLE_ADMIN,
        )

        self.doctor = User.objects.create_user(
            email='clinic-doctor-billing@example.com',
            cognito_sub='clinic-doctor-billing-sub',
            role='CLINIC_DOCTOR',
            clinic=self.clinic,
        )
        Membership.objects.create(
            account=self.clinic,
            user=self.doctor,
            role=Membership.ROLE_DOCTOR,
        )

    def test_clinic_admin_cannot_access_individual_billing_plans(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/auth/billing/plans/')
        self.assertEqual(response.status_code, 403)

    def test_clinic_admin_cannot_open_individual_billing_portal(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/auth/billing/portal/', {}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_clinic_doctor_cannot_access_individual_billing_plans(self):
        self.client.force_authenticate(user=self.doctor)
        response = self.client.get('/api/auth/billing/plans/')
        self.assertEqual(response.status_code, 403)

    def test_clinic_doctor_cannot_open_individual_billing_portal(self):
        self.client.force_authenticate(user=self.doctor)
        response = self.client.post('/api/auth/billing/portal/', {}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_clinic_admin_cannot_cancel_individual_subscription(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/auth/billing/cancel/', {}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_clinic_doctor_cannot_cancel_individual_subscription(self):
        self.client.force_authenticate(user=self.doctor)
        response = self.client.post('/api/auth/billing/cancel/', {}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_clinic_admin_cannot_sync_individual_billing(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/auth/billing/sync/', {}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_clinic_doctor_cannot_sync_individual_billing(self):
        self.client.force_authenticate(user=self.doctor)
        response = self.client.post('/api/auth/billing/sync/', {}, format='json')
        self.assertEqual(response.status_code, 403)
