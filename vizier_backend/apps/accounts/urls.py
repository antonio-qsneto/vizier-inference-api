"""
URLs for accounts app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import billing_views

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'categories', views.CategoriesViewSet, basename='category')

urlpatterns = [
    path('me/', views.UserViewSet.as_view({'get': 'me'}), name='user-me'),
    path('cognito/callback/', views.CognitoCallbackView.as_view(), name='cognito-callback'),
    path(
        'consultation-request/',
        views.ConsultationRequestView.as_view(),
        name='consultation-request',
    ),
    path('dev/signup/', views.DevMockSignupView.as_view(), name='dev-signup'),
    path('dev/login/', views.DevMockLoginView.as_view(), name='dev-login'),
    path('billing/plans/', billing_views.BillingPlansView.as_view(), name='billing-plans'),
    path('billing/checkout/', billing_views.BillingCheckoutView.as_view(), name='billing-checkout'),
    path('billing/sync/', billing_views.BillingSyncView.as_view(), name='billing-sync'),
    path('billing/cancel/', billing_views.BillingCancelView.as_view(), name='billing-cancel'),
    path('billing/portal/', billing_views.BillingPortalView.as_view(), name='billing-portal'),
    path('billing/webhook/', billing_views.StripeBillingWebhookView.as_view(), name='billing-webhook'),
    path('', include(router.urls)),
]
