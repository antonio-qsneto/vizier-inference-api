"""
URLs for tenants app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'clinics', views.ClinicViewSet, basename='clinic')
router.register(r'invitations', views.DoctorInvitationViewSet, basename='invitation')

urlpatterns = [
    path('', include(router.urls)),
]
