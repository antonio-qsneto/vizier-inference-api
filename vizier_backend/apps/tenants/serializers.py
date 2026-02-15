"""
Serializers for tenants app.
"""

from rest_framework import serializers
from .models import Clinic, DoctorInvitation, SubscriptionPlan, Subscription
from apps.accounts.serializers import UserSerializer


class ClinicSerializer(serializers.ModelSerializer):
    """Serializer for Clinic model."""
    
    owner = UserSerializer(read_only=True)
    active_doctors_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Clinic
        fields = [
            'id',
            'name',
            'cnpj',
            'owner',
            'seat_limit',
            'subscription_plan',
            'active_doctors_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at']
    
    def get_active_doctors_count(self, obj):
        """Get count of active doctors."""
        return obj.get_active_doctors_count()


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
