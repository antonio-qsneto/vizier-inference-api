"""
Serializers for accounts app.
"""

from rest_framework import serializers
from .models import User, UserNotice, UserSubscription
from .rbac import RBACRole, resolve_effective_role


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
    seat_used = serializers.SerializerMethodField()
    account_status = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    effective_role = serializers.SerializerMethodField()
    notices = serializers.SerializerMethodField()
    account_lifecycle_status = serializers.CharField(read_only=True)
    upload_enabled = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'full_name',
            'first_name',
            'last_name',
            'role',
            'effective_role',
            'clinic_id',
            'clinic_name',
            'subscription_plan',
            'seat_limit',
            'seat_used',
            'account_status',
            'account_lifecycle_status',
            'upload_enabled',
            'notices',
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
            if resolve_effective_role(obj) == RBACRole.CLINIC_DOCTOR:
                return None
            if obj.clinic.can_use_clinic_resources():
                return obj.clinic.subscription_plan
            return 'free'

        subscription = UserSubscription.objects.filter(user=obj).first()
        if subscription and subscription.has_active_access():
            return subscription.plan

        return 'free'
    
    def get_seat_limit(self, obj):
        """Get seat limit."""
        if obj.clinic:
            if resolve_effective_role(obj) == RBACRole.CLINIC_DOCTOR:
                return None
            return obj.clinic.seat_limit
        return None

    def get_seat_used(self, obj):
        if obj.clinic:
            if resolve_effective_role(obj) == RBACRole.CLINIC_DOCTOR:
                return None
            return obj.clinic.get_seat_usage()
        return None

    def get_account_status(self, obj):
        if obj.clinic:
            if resolve_effective_role(obj) == RBACRole.CLINIC_DOCTOR:
                return None
            return obj.clinic.account_status
        return None
    
    def get_full_name(self, obj):
        """Get full name."""
        return obj.get_full_name()

    def get_effective_role(self, obj):
        return resolve_effective_role(obj)

    def get_notices(self, obj):
        pending_notices = obj.notices.filter(acknowledged_at__isnull=True).order_by('-created_at')
        return UserNoticeSerializer(pending_notices, many=True).data

    def get_upload_enabled(self, obj):
        try:
            return bool(obj.has_upload_access())
        except Exception:
            return False


class UserNoticeSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserNotice
        fields = [
            'id',
            'type',
            'title',
            'message',
            'payload',
            'created_at',
        ]
        read_only_fields = fields


class AcknowledgeNoticesSerializer(serializers.Serializer):
    notice_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )


class DeleteAccountSerializer(serializers.Serializer):
    confirm_text = serializers.CharField()
    current_password = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        write_only=True,
    )


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


class ConsultationRequestSerializer(serializers.Serializer):
    """Serializer for public consultation requests from the marketing site."""

    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    company_name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    job_title = serializers.CharField(required=False, allow_blank=True, max_length=150)
    email = serializers.EmailField()
    country = serializers.CharField(max_length=100)
    message = serializers.CharField(required=False, allow_blank=True, max_length=4000)
    discovery_source = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
    )

    def validate_email(self, value):
        return value.strip().lower()

    def validate_country(self, value):
        return value.strip()

    def validate(self, attrs):
        for field in (
            "first_name",
            "last_name",
            "company_name",
            "job_title",
            "message",
            "discovery_source",
        ):
            if field in attrs and isinstance(attrs[field], str):
                attrs[field] = attrs[field].strip()

        return attrs


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


class BillingSyncSerializer(serializers.Serializer):
    """Payload for explicit individual billing synchronization."""

    checkout_session_id = serializers.CharField(required=False, allow_blank=False)
