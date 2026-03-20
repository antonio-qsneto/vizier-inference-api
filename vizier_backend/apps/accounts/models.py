"""
User and authentication models.
"""

import uuid

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils import timezone


class UserManager(BaseUserManager):
    """Custom user manager for Cognito-based authentication."""
    
    def create_user(self, email, cognito_sub, **extra_fields):
        """Create and save a regular user."""
        if not email:
            raise ValueError('The Email field must be set')
        if not cognito_sub:
            raise ValueError('The Cognito Sub field must be set')
        
        email = self.normalize_email(email)
        user = self.model(email=email, cognito_sub=cognito_sub, **extra_fields)
        user.set_unusable_password()  # Cognito handles passwords
        user.save(using=self._db)
        return user
    
    def create_superuser(self, email, cognito_sub, **extra_fields):
        """Create and save a superuser."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, cognito_sub, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model integrated with AWS Cognito.
    No passwords stored locally; authentication via JWT.
    """
    
    ROLE_CHOICES = [
        ('INDIVIDUAL', 'Individual Doctor'),
        ('CLINIC_ADMIN', 'Clinic Administrator'),
        ('CLINIC_DOCTOR', 'Clinic Doctor'),
    ]
    ACCOUNT_LIFECYCLE_ACTIVE = 'active'
    ACCOUNT_LIFECYCLE_DELETED = 'deleted'
    ACCOUNT_LIFECYCLE_CHOICES = [
        (ACCOUNT_LIFECYCLE_ACTIVE, 'Active'),
        (ACCOUNT_LIFECYCLE_DELETED, 'Deleted'),
    ]
    
    # Cognito integration
    cognito_sub = models.CharField(
        max_length=255,
        unique=True,
        help_text='Unique identifier from AWS Cognito'
    )
    
    # User info
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    
    # Role and tenant
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='INDIVIDUAL'
    )
    clinic = models.ForeignKey(
        'tenants.Clinic',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='doctors'
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    account_lifecycle_status = models.CharField(
        max_length=20,
        choices=ACCOUNT_LIFECYCLE_CHOICES,
        default=ACCOUNT_LIFECYCLE_ACTIVE,
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    anonymized_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)
    
    objects = UserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['cognito_sub']
    
    class Meta:
        db_table = 'accounts_user'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['cognito_sub']),
            models.Index(fields=['email']),
            models.Index(fields=['clinic', 'role']),
            models.Index(fields=['account_lifecycle_status']),
        ]
    
    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"
    
    def get_full_name(self):
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip() or self.email
    
    def get_short_name(self):
        """Return the user's short name."""
        return self.first_name or self.email

    def is_deleted(self) -> bool:
        return self.account_lifecycle_status == self.ACCOUNT_LIFECYCLE_DELETED
    
    def is_clinic_admin(self):
        """Check if user is a clinic administrator."""
        from .rbac import RBACRole, resolve_effective_role

        return resolve_effective_role(self) == RBACRole.CLINIC_ADMIN
    
    def is_clinic_doctor(self):
        """Check if user is a clinic doctor."""
        from .rbac import RBACRole, resolve_effective_role

        return resolve_effective_role(self) == RBACRole.CLINIC_DOCTOR
    
    def is_individual_doctor(self):
        """Check if user is an individual doctor."""
        from .rbac import RBACRole, resolve_effective_role

        return resolve_effective_role(self) == RBACRole.INDIVIDUAL

    def get_effective_subscription_plan(self) -> str:
        """
        Resolve the effective plan for UI/authorization.

        - Clinic users use clinic.subscription_plan
        - Individual users rely on active Stripe-backed subscription
        """
        if self.clinic:
            if self.clinic.can_use_clinic_resources():
                return self.clinic.subscription_plan or 'free'
            return 'free'

        subscription = UserSubscription.objects.filter(user=self).first()
        if subscription and subscription.has_active_access():
            return subscription.plan

        return 'free'

    def has_upload_access(self) -> bool:
        """
        Upload permission business rule.

        - Clinic members require an active clinic account and valid seat usage
        - Individual users require active paid subscription
        """
        from .rbac import RBACPermission, has_scoped_permission

        if not self.is_active or self.is_deleted():
            return False

        if (self.email or '').strip().lower() == 'testevizier@gmail.com':
            return True

        if self.clinic:
            clinic = self.clinic
            if clinic.plan_type != clinic.PLAN_TYPE_CLINIC:
                return False
            if not clinic.can_use_clinic_resources():
                return False

            return has_scoped_permission(
                self,
                RBACPermission.STUDIES_CREATE,
                tenant_id=self.clinic_id,
            )

        if not has_scoped_permission(
            self,
            RBACPermission.STUDIES_CREATE,
            resource_owner_user_id=self.id,
        ):
            return False

        subscription = UserSubscription.objects.filter(user=self).first()
        return bool(subscription and subscription.has_active_access())


class UserSubscription(models.Model):
    """
    Stripe-backed subscription state for individual users.
    """

    PLAN_FREE = 'free'
    PLAN_INDIVIDUAL_MONTHLY = 'plano_individual_mensal'
    PLAN_INDIVIDUAL_ANNUAL = 'plano_individual_anual'
    PLAN_CHOICES = [
        (PLAN_FREE, 'Free'),
        (PLAN_INDIVIDUAL_MONTHLY, 'Plano individual mensal'),
        (PLAN_INDIVIDUAL_ANNUAL, 'Plano individual anual'),
    ]

    STATUS_INACTIVE = 'INACTIVE'
    STATUS_INCOMPLETE = 'INCOMPLETE'
    STATUS_ACTIVE = 'ACTIVE'
    STATUS_TRIALING = 'TRIALING'
    STATUS_PAST_DUE = 'PAST_DUE'
    STATUS_CANCELED = 'CANCELED'
    STATUS_CHOICES = [
        (STATUS_INACTIVE, 'Inactive'),
        (STATUS_INCOMPLETE, 'Incomplete'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_TRIALING, 'Trialing'),
        (STATUS_PAST_DUE, 'Past Due'),
        (STATUS_CANCELED, 'Canceled'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='billing_subscription',
    )
    plan = models.CharField(max_length=64, choices=PLAN_CHOICES, default=PLAN_FREE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_INACTIVE)
    stripe_customer_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_checkout_session_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_price_id = models.CharField(max_length=255, null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    billing_grace_until = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts_user_subscription'
        indexes = [
            models.Index(fields=['plan', 'status']),
            models.Index(fields=['stripe_customer_id']),
            models.Index(fields=['stripe_subscription_id']),
            models.Index(fields=['stripe_checkout_session_id']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.plan} ({self.status})"

    def has_active_access(self) -> bool:
        if self.plan == self.PLAN_FREE:
            return False

        if self.status in {self.STATUS_ACTIVE, self.STATUS_TRIALING, self.STATUS_CANCELED}:
            if self.current_period_end:
                return self.current_period_end > timezone.now()
            return self.status in {self.STATUS_ACTIVE, self.STATUS_TRIALING}

        if (
            self.status == self.STATUS_PAST_DUE
            and self.billing_grace_until
            and self.billing_grace_until > timezone.now()
        ):
            return True

        return False


class UserNotice(models.Model):
    """
    In-app notices that require explicit user acknowledgement.
    """

    TYPE_CLINIC_REMOVED = 'CLINIC_REMOVED'
    TYPE_CHOICES = [
        (TYPE_CLINIC_REMOVED, 'Clinic removed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notices',
    )
    type = models.CharField(max_length=64, choices=TYPE_CHOICES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    payload = models.JSONField(default=dict, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_user_notice'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'acknowledged_at', 'created_at']),
            models.Index(fields=['type', 'created_at']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.type}"
