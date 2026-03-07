"""
Serializers for accounts app.
"""

from rest_framework import serializers
from .models import User, UserSubscription


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""
    
    clinic_id = serializers.SerializerMethodField()
    clinic_name = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'full_name',
            'first_name',
            'last_name',
            'role',
            'clinic_id',
            'clinic_name',
            'is_active',
            'created_at',
        ]
        read_only_fields = fields
    
    def get_clinic_id(self, obj):
        """Get clinic ID."""
        return str(obj.clinic.id) if obj.clinic else None
    
    def get_clinic_name(self, obj):
        """Get clinic name."""
        return obj.clinic.name if obj.clinic else None
    
    def get_full_name(self, obj):
        """Get full name."""
        return obj.get_full_name()


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile with subscription info."""
    
    clinic_id = serializers.SerializerMethodField()
    clinic_name = serializers.SerializerMethodField()
    subscription_plan = serializers.SerializerMethodField()
    seat_limit = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'full_name',
            'first_name',
            'last_name',
            'role',
            'clinic_id',
            'clinic_name',
            'subscription_plan',
            'seat_limit',
            'is_active',
            'created_at',
        ]
        read_only_fields = fields
    
    def get_clinic_id(self, obj):
        """Get clinic ID."""
        return str(obj.clinic.id) if obj.clinic else None
    
    def get_clinic_name(self, obj):
        """Get clinic name."""
        return obj.clinic.name if obj.clinic else None
    
    def get_subscription_plan(self, obj):
        """Get subscription plan."""
        if obj.clinic:
            return obj.clinic.subscription_plan

        subscription = UserSubscription.objects.filter(user=obj).first()
        if subscription and subscription.has_active_access():
            return subscription.plan

        return 'free'
    
    def get_seat_limit(self, obj):
        """Get seat limit."""
        if obj.clinic:
            return obj.clinic.seat_limit
        return None
    
    def get_full_name(self, obj):
        """Get full name."""
        return obj.get_full_name()


class DevMockSignupSerializer(serializers.Serializer):
    """Serializer for development mock user signup."""

    email = serializers.EmailField()
    password = serializers.CharField(
        min_length=6,
        max_length=128,
        trim_whitespace=False,
        write_only=True,
    )
    first_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    last_name = serializers.CharField(max_length=150, allow_blank=True, required=False)

    def validate_email(self, value):
        return value.strip().lower()


class DevMockLoginSerializer(serializers.Serializer):
    """Serializer for development mock user login."""

    email = serializers.EmailField()
    password = serializers.CharField(
        min_length=6,
        max_length=128,
        trim_whitespace=False,
        write_only=True,
    )

    def validate_email(self, value):
        return value.strip().lower()


class BillingCheckoutSerializer(serializers.Serializer):
    """Payload for Stripe checkout session creation."""

    plan_id = serializers.ChoiceField(
        choices=[
            UserSubscription.PLAN_INDIVIDUAL_MONTHLY,
            UserSubscription.PLAN_INDIVIDUAL_ANNUAL,
        ]
    )
    current_password = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        write_only=True,
    )
    success_url = serializers.URLField(required=False)
    cancel_url = serializers.URLField(required=False)


class BillingPortalSerializer(serializers.Serializer):
    """Payload for Stripe customer portal."""

    return_url = serializers.URLField(required=False)
