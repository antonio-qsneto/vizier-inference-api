"""
RBAC policy for API authorization with tenant/resource scopes.

This module centralizes:
- role -> permissions matrix
- permission scope requirements
- effective-role resolution from membership (with legacy fallback)
- scoped authorization checks
"""

from __future__ import annotations

from typing import Any

from django.apps import apps


class RBACRole:
    PLATFORM_ADMIN = 'platform_admin'
    CLINIC_ADMIN = 'clinic_admin'
    CLINIC_DOCTOR = 'clinic_doctor'
    INDIVIDUAL = 'individual'


class RBACPermission:
    USERS_READ_SELF = 'users.read.self'
    USERS_READ_TENANT = 'users.read.tenant'

    STUDIES_CREATE = 'studies.create'
    STUDIES_READ = 'studies.read'
    STUDIES_RESULTS_READ = 'studies.results.read'

    BILLING_INDIVIDUAL_MANAGE = 'billing.individual.manage'
    BILLING_CLINIC_MANAGE = 'billing.clinic.manage'

    CLINIC_TEAM_MANAGE = 'clinic.team.manage'


class RBACScope:
    GLOBAL = 'global'
    TENANT = 'tenant'
    RESOURCE_OWNER = 'resource_owner'
    TENANT_OR_OWNER = 'tenant_or_owner'


ROLE_PERMISSION_MATRIX: dict[str, set[str]] = {
    RBACRole.PLATFORM_ADMIN: {'*'},
    RBACRole.CLINIC_ADMIN: {
        RBACPermission.USERS_READ_SELF,
        RBACPermission.USERS_READ_TENANT,
        RBACPermission.STUDIES_READ,
        RBACPermission.STUDIES_RESULTS_READ,
        RBACPermission.BILLING_CLINIC_MANAGE,
        RBACPermission.CLINIC_TEAM_MANAGE,
    },
    RBACRole.CLINIC_DOCTOR: {
        RBACPermission.USERS_READ_SELF,
        RBACPermission.STUDIES_CREATE,
        RBACPermission.STUDIES_READ,
        RBACPermission.STUDIES_RESULTS_READ,
    },
    RBACRole.INDIVIDUAL: {
        RBACPermission.USERS_READ_SELF,
        RBACPermission.STUDIES_CREATE,
        RBACPermission.STUDIES_READ,
        RBACPermission.STUDIES_RESULTS_READ,
        RBACPermission.BILLING_INDIVIDUAL_MANAGE,
    },
}


PERMISSION_SCOPE_MATRIX: dict[str, str] = {
    RBACPermission.USERS_READ_SELF: RBACScope.RESOURCE_OWNER,
    RBACPermission.USERS_READ_TENANT: RBACScope.TENANT,
    RBACPermission.STUDIES_CREATE: RBACScope.TENANT_OR_OWNER,
    RBACPermission.STUDIES_READ: RBACScope.TENANT_OR_OWNER,
    RBACPermission.STUDIES_RESULTS_READ: RBACScope.TENANT_OR_OWNER,
    RBACPermission.BILLING_INDIVIDUAL_MANAGE: RBACScope.RESOURCE_OWNER,
    RBACPermission.BILLING_CLINIC_MANAGE: RBACScope.TENANT,
    RBACPermission.CLINIC_TEAM_MANAGE: RBACScope.TENANT,
}


def _safe_getattr(obj: Any, field: str, default: Any = None) -> Any:
    if obj is None:
        return default
    return getattr(obj, field, default)


def _resolve_membership_role(user) -> str | None:
    user_id = _safe_getattr(user, 'id')
    clinic_id = _safe_getattr(user, 'clinic_id')
    if not user_id or not clinic_id:
        return None

    Membership = apps.get_model('tenants', 'Membership')
    return (
        Membership.objects.filter(account_id=clinic_id, user_id=user_id)
        .values_list('role', flat=True)
        .first()
    )


def resolve_effective_role(user) -> str | None:
    """
    Resolve effective RBAC role.

    Priority:
    1) platform admin (staff/superuser)
    2) active clinic membership role
    3) legacy user.role fallback when clinic is attached
    4) individual
    """
    if not user or not _safe_getattr(user, 'is_authenticated', False):
        return None

    if _safe_getattr(user, 'is_superuser', False) or _safe_getattr(user, 'is_staff', False):
        return RBACRole.PLATFORM_ADMIN

    membership_role = _resolve_membership_role(user)
    if membership_role == 'admin':
        return RBACRole.CLINIC_ADMIN
    if membership_role == 'doctor':
        return RBACRole.CLINIC_DOCTOR

    clinic_id = _safe_getattr(user, 'clinic_id')
    legacy_role = str(_safe_getattr(user, 'role', '') or '')
    if clinic_id and legacy_role == 'CLINIC_ADMIN':
        return RBACRole.CLINIC_ADMIN
    if clinic_id and legacy_role == 'CLINIC_DOCTOR':
        return RBACRole.CLINIC_DOCTOR

    return RBACRole.INDIVIDUAL


def _permission_set_for_role(role: str | None) -> set[str]:
    return ROLE_PERMISSION_MATRIX.get(role or '', set())


def _is_global_role(role: str | None) -> bool:
    return role == RBACRole.PLATFORM_ADMIN


def _same_scope_value(left: Any, right: Any) -> bool:
    return str(left) == str(right)


def _scope_matches(
    *,
    scope: str,
    actor_tenant_id: Any,
    actor_user_id: Any,
    tenant_id: Any = None,
    resource_owner_user_id: Any = None,
) -> bool:
    if scope == RBACScope.GLOBAL:
        return True

    if scope == RBACScope.TENANT:
        target_tenant_id = tenant_id if tenant_id is not None else actor_tenant_id
        if actor_tenant_id is None or target_tenant_id is None:
            return False
        return _same_scope_value(actor_tenant_id, target_tenant_id)

    if scope == RBACScope.RESOURCE_OWNER:
        target_owner_id = (
            resource_owner_user_id if resource_owner_user_id is not None else actor_user_id
        )
        if actor_user_id is None or target_owner_id is None:
            return False
        return _same_scope_value(actor_user_id, target_owner_id)

    if scope == RBACScope.TENANT_OR_OWNER:
        if tenant_id is not None:
            return _scope_matches(
                scope=RBACScope.TENANT,
                actor_tenant_id=actor_tenant_id,
                actor_user_id=actor_user_id,
                tenant_id=tenant_id,
            )
        if resource_owner_user_id is not None:
            return _scope_matches(
                scope=RBACScope.RESOURCE_OWNER,
                actor_tenant_id=actor_tenant_id,
                actor_user_id=actor_user_id,
                resource_owner_user_id=resource_owner_user_id,
            )

        if actor_tenant_id is not None:
            return True
        return actor_user_id is not None

    return False


def has_scoped_permission(
    user,
    permission: str,
    *,
    tenant_id: Any = None,
    resource_owner_user_id: Any = None,
) -> bool:
    role = resolve_effective_role(user)
    if role is None:
        return False

    if _is_global_role(role):
        return True

    permission_set = _permission_set_for_role(role)
    if permission not in permission_set:
        return False

    required_scope = PERMISSION_SCOPE_MATRIX.get(permission, RBACScope.GLOBAL)
    return _scope_matches(
        scope=required_scope,
        actor_tenant_id=_safe_getattr(user, 'clinic_id'),
        actor_user_id=_safe_getattr(user, 'id'),
        tenant_id=tenant_id,
        resource_owner_user_id=resource_owner_user_id,
    )
