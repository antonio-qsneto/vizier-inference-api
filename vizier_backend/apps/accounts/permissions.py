"""
Custom permissions for Django REST Framework.
"""

from rest_framework.permissions import BasePermission


class IsClinicAdmin(BasePermission):
    """
    Permission to check if user is a clinic administrator.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role == 'CLINIC_ADMIN'
        )


class IsClinicDoctor(BasePermission):
    """
    Permission to check if user is a clinic doctor.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role == 'CLINIC_DOCTOR'
        )


class IsIndividualDoctor(BasePermission):
    """
    Permission to check if user is an individual doctor.
    """
    
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role == 'INDIVIDUAL'
        )


class IsTenantMember(BasePermission):
    """
    Permission to check if user belongs to a specific tenant (clinic).
    """
    
    def has_object_permission(self, request, view, obj):
        """
        Check if user's clinic matches the object's clinic.
        """
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Get clinic from object
        clinic = getattr(obj, 'clinic', None)
        if not clinic:
            return False
        
        # Check if user belongs to the clinic
        return request.user.clinic == clinic or request.user.clinic_id == clinic.id


class TenantQuerySetMixin:
    """
    Mixin to filter queryset by tenant (clinic).
    """
    
    def get_queryset(self):
        """
        Filter queryset by user's clinic.
        """
        queryset = super().get_queryset()
        
        if not self.request.user or not self.request.user.is_authenticated:
            return queryset.none()
        
        # Clinic members: tenant-scoped access.
        if self.request.user.clinic:
            return queryset.filter(clinic=self.request.user.clinic)

        # Individual users (no clinic): owner-scoped access when supported.
        if hasattr(queryset.model, 'owner'):
            return queryset.filter(owner=self.request.user)

        return queryset.none()
