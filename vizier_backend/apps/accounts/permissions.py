"""
Custom permissions for Django REST Framework.
"""

from rest_framework.permissions import BasePermission

from .rbac import RBACPermission, RBACRole, has_scoped_permission, resolve_effective_role


def _current_tenant_id(request):
    return getattr(getattr(request, 'user', None), 'clinic_id', None)


def _current_user_id(request):
    return getattr(getattr(request, 'user', None), 'id', None)


class IsClinicAdmin(BasePermission):
    """
    Backward-compatible alias for clinic team manager permission.
    """

    def has_permission(self, request, view):
        return has_scoped_permission(
            request.user,
            RBACPermission.CLINIC_TEAM_MANAGE,
            tenant_id=_current_tenant_id(request),
        )


class IsClinicDoctor(BasePermission):
    """
    Permission to check if user's effective RBAC role is clinic doctor.
    """

    def has_permission(self, request, view):
        return resolve_effective_role(request.user) == RBACRole.CLINIC_DOCTOR


class IsIndividualDoctor(BasePermission):
    """
    Permission to check if user's effective RBAC role is individual.
    """

    def has_permission(self, request, view):
        return resolve_effective_role(request.user) == RBACRole.INDIVIDUAL


class CanManageClinicBilling(BasePermission):
    """
    Permission for clinic billing operations.
    """

    def has_permission(self, request, view):
        return has_scoped_permission(
            request.user,
            RBACPermission.BILLING_CLINIC_MANAGE,
            tenant_id=_current_tenant_id(request),
        )


class CanManageClinicTeam(BasePermission):
    """
    Permission for clinic team operations (invites, listing, removals).
    """

    def has_permission(self, request, view):
        return has_scoped_permission(
            request.user,
            RBACPermission.CLINIC_TEAM_MANAGE,
            tenant_id=_current_tenant_id(request),
        )


class CanManageIndividualBilling(BasePermission):
    """
    Permission for individual billing operations.
    """

    def has_permission(self, request, view):
        return has_scoped_permission(
            request.user,
            RBACPermission.BILLING_INDIVIDUAL_MANAGE,
            resource_owner_user_id=_current_user_id(request),
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

        clinic = getattr(obj, 'clinic', None)
        if clinic:
            return has_scoped_permission(
                request.user,
                RBACPermission.STUDIES_READ,
                tenant_id=getattr(clinic, 'id', clinic),
            )

        owner_id = getattr(obj, 'owner_id', None)
        if owner_id is not None:
            return has_scoped_permission(
                request.user,
                RBACPermission.STUDIES_READ,
                resource_owner_user_id=owner_id,
            )

        return False


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

        tenant_permission = getattr(self, 'tenant_scope_permission', RBACPermission.STUDIES_READ)
        owner_permission = getattr(self, 'owner_scope_permission', RBACPermission.STUDIES_READ)

        user = self.request.user
        if user.is_staff or user.is_superuser:
            return queryset

        if user.clinic_id and hasattr(queryset.model, 'clinic') and has_scoped_permission(
            user,
            tenant_permission,
            tenant_id=user.clinic_id,
        ):
            return queryset.filter(clinic_id=user.clinic_id)

        if hasattr(queryset.model, 'owner') and has_scoped_permission(
            user,
            owner_permission,
            resource_owner_user_id=user.id,
        ):
            return queryset.filter(owner=user)

        return queryset.none()
