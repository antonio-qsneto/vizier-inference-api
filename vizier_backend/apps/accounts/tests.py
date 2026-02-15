"""
Tests for accounts app.
"""

from django.test import TestCase, Client
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from .models import User
from apps.tenants.models import Clinic


class UserModelTest(TestCase):
    """Test User model."""
    
    def setUp(self):
        """Set up test user."""
        # Create owner first
        owner = User.objects.create_user(
            email="owner@example.com",
            cognito_sub="owner-cognito-sub",
            first_name="Owner",
            last_name="User"
        )
        self.clinic = Clinic.objects.create(
            name="Test Clinic",
            cnpj="12345678000190",
            owner=owner
        )
        self.user = User.objects.create_user(
            email="test@example.com",
            cognito_sub="test-cognito-sub",
            first_name="Test",
            last_name="User",
            clinic=self.clinic
        )
    
    def test_user_creation(self):
        """Test user creation."""
        self.assertEqual(self.user.email, "test@example.com")
        self.assertEqual(self.user.clinic, self.clinic)
        self.assertTrue(self.user.is_active)
    
    def test_user_full_name(self):
        """Test user full name."""
        self.assertEqual(self.user.get_full_name(), "Test User")
    
    def test_user_str(self):
        """Test user string representation."""
        self.assertIn("test@example.com", str(self.user))
