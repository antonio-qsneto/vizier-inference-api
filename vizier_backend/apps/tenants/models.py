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
    
    # Subscription placeholders (for future Stripe integration)
    seat_limit = models.IntegerField(default=5)
    subscription_plan = models.CharField(
        max_length=50,
        default='free',
        choices=[
            ('free', 'Free'),
            ('starter', 'Starter'),
            ('professional', 'Professional'),
            ('enterprise', 'Enterprise'),
        ]
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'tenants_clinic'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['owner']),
            models.Index(fields=['cnpj']),
        ]
    
    def __str__(self):
        return self.name
    
    def get_active_doctors_count(self):
        """Count active doctors in the clinic."""
        return self.doctors.filter(is_active=True).count()
    
    def can_add_doctor(self):
        """Check if clinic can add more doctors (seat limit)."""
        if not self.seat_limit:
            return True
        return self.get_active_doctors_count() < self.seat_limit


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
