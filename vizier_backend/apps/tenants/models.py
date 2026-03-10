"""
Tenant (Clinic) and related models.
"""

from django.db import models
from django.utils import timezone
import uuid


class Clinic(models.Model):
    """
    Clinic model representing a tenant in the SaaS system.
    """

    PLAN_TYPE_INDIVIDUAL = 'individual'
    PLAN_TYPE_CLINIC = 'clinic'
    PLAN_TYPE_CHOICES = [
        (PLAN_TYPE_INDIVIDUAL, 'Individual'),
        (PLAN_TYPE_CLINIC, 'Clinic'),
    ]

    ACCOUNT_STATUS_ACTIVE = 'active'
    ACCOUNT_STATUS_PAST_DUE = 'past_due'
    ACCOUNT_STATUS_CANCELED = 'canceled'
    ACCOUNT_STATUS_CHOICES = [
        (ACCOUNT_STATUS_ACTIVE, 'Active'),
        (ACCOUNT_STATUS_PAST_DUE, 'Past due'),
        (ACCOUNT_STATUS_CANCELED, 'Canceled'),
    ]

    SUBSCRIPTION_PLAN_FREE = 'free'
    SUBSCRIPTION_PLAN_CLINIC_MONTHLY = 'clinic_monthly'
    SUBSCRIPTION_PLAN_CLINIC_YEARLY = 'clinic_yearly'
    SUBSCRIPTION_PLAN_CHOICES = [
        (SUBSCRIPTION_PLAN_FREE, 'Free'),
        (SUBSCRIPTION_PLAN_CLINIC_MONTHLY, 'Clinic monthly'),
        (SUBSCRIPTION_PLAN_CLINIC_YEARLY, 'Clinic yearly'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Basic info
    name = models.CharField(max_length=255)
    cnpj = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text='CNPJ for LGPD compliance'
    )
    
    # Owner
    owner = models.OneToOneField(
        'accounts.User',
        on_delete=models.PROTECT,
        related_name='owned_clinic'
    )

    # Stripe billing state (account-level subscription).
    seat_limit = models.PositiveIntegerField(
        default=0,
        help_text='Seat limit mirrored from Stripe subscription item quantity.',
    )
    subscription_plan = models.CharField(
        max_length=50,
        default=SUBSCRIPTION_PLAN_FREE,
        choices=SUBSCRIPTION_PLAN_CHOICES,
    )
    plan_type = models.CharField(
        max_length=20,
        choices=PLAN_TYPE_CHOICES,
        default=PLAN_TYPE_CLINIC,
    )
    account_status = models.CharField(
        max_length=20,
        choices=ACCOUNT_STATUS_CHOICES,
        default=ACCOUNT_STATUS_CANCELED,
    )
    stripe_customer_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_subscription_item_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_price_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_current_period_end = models.DateTimeField(null=True, blank=True)
    billing_grace_until = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)
    scheduled_seat_limit = models.PositiveIntegerField(null=True, blank=True)
    scheduled_seat_effective_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tenants_clinic'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner']),
            models.Index(fields=['cnpj']),
            models.Index(fields=['stripe_customer_id']),
            models.Index(fields=['stripe_subscription_id']),
            models.Index(fields=['account_status']),
        ]
    
    def __str__(self):
        return self.name

    def is_yearly_plan(self) -> bool:
        return self.subscription_plan == self.SUBSCRIPTION_PLAN_CLINIC_YEARLY

    def has_active_subscription(self) -> bool:
        return (
            self.account_status == self.ACCOUNT_STATUS_ACTIVE
            and bool(self.stripe_subscription_id)
        )

    def get_seat_limit(self) -> int:
        return int(self.seat_limit or 0)

    def get_active_doctors_count(self):
        """Count active doctor seats using Membership records + legacy fallback."""
        if self.plan_type == self.PLAN_TYPE_INDIVIDUAL:
            return 1 if self.owner and self.owner.is_active else 0

        membership_user_ids = set(
            self.memberships.filter(
                role=Membership.ROLE_DOCTOR,
                user__is_active=True,
            ).values_list('user_id', flat=True)
        )
        legacy_user_ids = set(
            self.doctors.filter(
                is_active=True,
                role='CLINIC_DOCTOR',
            ).values_list('id', flat=True)
        )

        return len(membership_user_ids.union(legacy_user_ids))

    def get_seat_usage(self) -> int:
        return self.get_active_doctors_count()

    def can_add_doctor(self, increment: int = 1) -> bool:
        """Check if the account can add N more doctors under current seat limit."""
        if increment <= 0:
            return True
        return (self.get_seat_usage() + increment) <= self.get_seat_limit()

    def has_valid_seat_usage(self) -> bool:
        return self.get_seat_usage() <= self.get_seat_limit()

    def can_use_clinic_resources(self) -> bool:
        account_is_usable = self.account_status == self.ACCOUNT_STATUS_ACTIVE
        if (
            not account_is_usable
            and self.account_status == self.ACCOUNT_STATUS_PAST_DUE
            and self.billing_grace_until
            and self.billing_grace_until > timezone.now()
        ):
            account_is_usable = True
        if (
            not account_is_usable
            and self.account_status == self.ACCOUNT_STATUS_CANCELED
            and self.stripe_current_period_end
            and self.stripe_current_period_end > timezone.now()
        ):
            account_is_usable = True

        if not account_is_usable:
            return False
        if self.get_seat_limit() <= 0:
            return False
        return self.has_valid_seat_usage()


class Membership(models.Model):
    """
    Account membership model.

    Stripe quantity for clinic subscriptions must match the number of memberships
    with role=doctor for each account.
    """

    ROLE_ADMIN = 'admin'
    ROLE_DOCTOR = 'doctor'
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Admin'),
        (ROLE_DOCTOR, 'Doctor'),
    ]

    account = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_DOCTOR,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tenants_membership'
        indexes = [
            models.Index(fields=['account', 'role']),
            models.Index(fields=['user']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['account', 'user'],
                name='tenants_membership_unique_account_user',
            ),
        ]

    def __str__(self):
        return f"{self.user.email} @ {self.account.name} ({self.role})"


class DoctorInvitation(models.Model):
    """
    Invitation for doctors to join a clinic.
    """
    
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('ACCEPTED', 'Accepted'),
        ('REMOVED', 'Removed'),
        ('REJECTED', 'Rejected'),
        ('EXPIRED', 'Expired'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Invitation details
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        related_name='doctor_invitations'
    )
    email = models.EmailField()
    invited_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='sent_invitations'
    )
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'tenants_doctor_invitation'
        ordering = ['-created_at']
        unique_together = [['clinic', 'email']]
        indexes = [
            models.Index(fields=['clinic', 'status']),
            models.Index(fields=['email']),
        ]
    
    def __str__(self):
        return f"Invitation for {self.email} to {self.clinic.name}"
    
    def is_expired(self):
        """Check if invitation has expired."""
        return timezone.now() > self.expires_at
    
    def accept(self):
        """Mark invitation as accepted."""
        self.status = 'ACCEPTED'
        self.accepted_at = timezone.now()
        self.save()


class SubscriptionPlan(models.Model):
    """
    Subscription plan model (placeholder for future Stripe integration).
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    name = models.CharField(max_length=100)
    stripe_product_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_price_id = models.CharField(max_length=255, blank=True, null=True)
    
    price = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    
    seat_limit = models.IntegerField()
    max_studies_per_month = models.IntegerField(null=True, blank=True)
    
    features = models.JSONField(default=dict)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tenants_subscription_plan'
        ordering = ['price']
    
    def __str__(self):
        return f"{self.name} - {self.price} {self.currency}"


class Subscription(models.Model):
    """
    Subscription model (placeholder for future Stripe integration).
    """
    
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('CANCELED', 'Canceled'),
        ('PAST_DUE', 'Past Due'),
        ('TRIALING', 'Trialing'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    clinic = models.OneToOneField(
        Clinic,
        on_delete=models.CASCADE,
        related_name='subscription'
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT
    )
    
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='ACTIVE'
    )
    
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tenants_subscription'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.clinic.name} - {self.plan.name}"


class StripeWebhookEvent(models.Model):
    """
    Idempotency record for Stripe webhook processing.
    """

    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=255)
    livemode = models.BooleanField(default=False)
    payload = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tenants_stripe_webhook_event'
        indexes = [
            models.Index(fields=['event_type', 'processed_at']),
        ]

    def __str__(self):
        return f"{self.event_type} ({self.event_id})"


class SubscriptionEventLedger(models.Model):
    """
    Ordered/idempotent ledger for billing subscription state changes.

    This ledger is used for both clinic (tenant) and individual billing flows.
    """

    OBJECT_TYPE_CLINIC = 'clinic'
    OBJECT_TYPE_INDIVIDUAL = 'individual'
    OBJECT_TYPE_CHOICES = [
        (OBJECT_TYPE_CLINIC, 'Clinic'),
        (OBJECT_TYPE_INDIVIDUAL, 'Individual'),
    ]

    SOURCE_WEBHOOK = 'webhook'
    SOURCE_RECONCILIATION = 'reconciliation'
    SOURCE_CHOICES = [
        (SOURCE_WEBHOOK, 'Webhook'),
        (SOURCE_RECONCILIATION, 'Reconciliation'),
    ]

    STATUS_PENDING = 'PENDING'
    STATUS_APPLIED = 'APPLIED'
    STATUS_IGNORED_STALE = 'IGNORED_STALE'
    STATUS_FAILED = 'FAILED'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_APPLIED, 'Applied'),
        (STATUS_IGNORED_STALE, 'Ignored stale'),
        (STATUS_FAILED, 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    object_type = models.CharField(max_length=20, choices=OBJECT_TYPE_CHOICES)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_WEBHOOK)
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.CASCADE,
        related_name='subscription_event_ledger_entries',
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        'accounts.User',
        on_delete=models.CASCADE,
        related_name='subscription_event_ledger_entries',
        null=True,
        blank=True,
    )
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_event_id = models.CharField(max_length=255, blank=True, null=True)
    event_type = models.CharField(max_length=255)
    event_created_at = models.DateTimeField()
    idempotency_key = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    payload = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tenants_subscription_event_ledger'
        indexes = [
            models.Index(fields=['object_type', 'event_created_at']),
            models.Index(fields=['clinic', 'event_created_at']),
            models.Index(fields=['user', 'event_created_at']),
            models.Index(fields=['status', 'processed_at']),
        ]

    def __str__(self):
        target = self.clinic_id or self.user_id
        return f"{self.object_type}:{target}:{self.event_type}:{self.status}"
