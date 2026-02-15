"""
Serializers for accounts app.
"""

from rest_framework import serializers
from .models import User


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
        return 'free'
    
    def get_seat_limit(self, obj):
        """Get seat limit."""
        if obj.clinic:
            return obj.clinic.seat_limit
        return None
    
    def get_full_name(self, obj):
        """Get full name."""
        return obj.get_full_name()
