"""
Serializers for tenants app.
"""

from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from .models import (
    Clinic,
    DoctorInvitation,
    Membership,
    Subscription,
    SubscriptionPlan,
)


class ClinicSerializer(serializers.ModelSerializer):
    """Serializer for Clinic model."""

    owner = UserSerializer(read_only=True)
    active_doctors_count = serializers.SerializerMethodField()
    seat_used = serializers.SerializerMethodField()
    has_pending_seat_reduction = serializers.SerializerMethodField()

    class Meta:
        model = Clinic
        fields = [
            'id',
            'name',
            'cnpj',
            'owner',
            'seat_limit',
            'seat_used',
            'subscription_plan',
            'plan_type',
            'account_status',
            'active_doctors_count',
            'scheduled_seat_limit',
            'scheduled_seat_effective_at',
            'has_pending_seat_reduction',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'owner',
            'seat_limit',
            'seat_used',
            'subscription_plan',
            'plan_type',
            'account_status',
            'active_doctors_count',
            'scheduled_seat_limit',
            'scheduled_seat_effective_at',
            'has_pending_seat_reduction',
            'created_at',
            'updated_at',
        ]

    def get_active_doctors_count(self, obj):
        """Get count of active doctors."""
        return obj.get_active_doctors_count()

    def get_seat_used(self, obj):
        return obj.get_seat_usage()

    def get_has_pending_seat_reduction(self, obj):
        return bool(obj.scheduled_seat_limit is not None)


class ClinicDoctorSerializer(serializers.ModelSerializer):
    """
    Redacted clinic representation for clinic doctors.
    """

    class Meta:
        model = Clinic
        fields = [
            'id',
            'name',
        ]
        read_only_fields = fields


class DoctorInvitationSerializer(serializers.ModelSerializer):
    """Serializer for DoctorInvitation model."""

    clinic_name = serializers.CharField(source='clinic.name', read_only=True)
    invited_by_email = serializers.CharField(source='invited_by.email', read_only=True)

    class Meta:
        model = DoctorInvitation
        fields = [
            'id',
            'clinic_name',
            'email',
            'invited_by_email',
            'status',
            'created_at',
            'expires_at',
            'accepted_at',
        ]
        read_only_fields = ['id', 'created_at', 'expires_at', 'accepted_at']


class DoctorInvitationCreateSerializer(serializers.Serializer):
    """Serializer for creating doctor invitations."""

    email = serializers.EmailField()

    def validate_email(self, value):
        """Validate email format."""
        return value.lower()


class MembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = [
            'id',
            'account',
            'user',
            'role',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class ClinicBillingCheckoutSerializer(serializers.Serializer):
    plan_id = serializers.ChoiceField(
        choices=[
            Clinic.SUBSCRIPTION_PLAN_CLINIC_MONTHLY,
            Clinic.SUBSCRIPTION_PLAN_CLINIC_YEARLY,
        ]
    )
    quantity = serializers.IntegerField(min_value=1, required=False)
    success_url = serializers.URLField(required=False)
    cancel_url = serializers.URLField(required=False)


class ClinicBillingPortalSerializer(serializers.Serializer):
    return_url = serializers.URLField(required=False)


class ClinicBillingSyncSerializer(serializers.Serializer):
    checkout_session_id = serializers.CharField(required=False, allow_blank=False)


class ClinicSeatUpdateSerializer(serializers.Serializer):
    target_quantity = serializers.IntegerField(min_value=1)


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """Serializer for SubscriptionPlan model."""

    class Meta:
        model = SubscriptionPlan
        fields = [
            'id',
            'name',
            'price',
            'currency',
            'seat_limit',
            'max_studies_per_month',
            'features',
        ]
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for Subscription model."""

    plan = SubscriptionPlanSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            'id',
            'clinic',
            'plan',
            'status',
            'current_period_start',
            'current_period_end',
            'created_at',
        ]
        read_only_fields = fields
