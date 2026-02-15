"""
User and authentication models.
"""

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
        ]
    
    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"
    
    def get_full_name(self):
        """Return the user's full name."""
        return f"{self.first_name} {self.last_name}".strip() or self.email
    
    def get_short_name(self):
        """Return the user's short name."""
        return self.first_name or self.email
    
    def is_clinic_admin(self):
        """Check if user is a clinic administrator."""
        return self.role == 'CLINIC_ADMIN'
    
    def is_clinic_doctor(self):
        """Check if user is a clinic doctor."""
        return self.role == 'CLINIC_DOCTOR'
    
    def is_individual_doctor(self):
        """Check if user is an individual doctor."""
        return self.role == 'INDIVIDUAL'
