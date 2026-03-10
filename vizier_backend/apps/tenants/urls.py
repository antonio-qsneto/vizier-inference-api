"""
URLs for tenants app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'clinics', views.ClinicViewSet, basename='clinic')
router.register(r'doctor-invitations', views.DoctorInvitationViewSet, basename='doctor-invitation')

urlpatterns = [
    path('billing/webhook/', views.ClinicStripeWebhookView.as_view(), name='clinic-billing-webhook'),
    path('', include(router.urls)),
]
