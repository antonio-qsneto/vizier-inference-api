from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.tenants.models import Clinic

User = get_user_model()


class UserTypeTest(TestCase):
    """Test different user types."""
    
    def setUp(self):
        """Create test clinic and users."""
        # Create owner
        self.owner = User.objects.create_user(
            email="owner@test.com",
            cognito_sub="owner-sub",
            first_name="Owner",
            last_name="User",
            role='CLINIC_ADMIN'
        )
        
        # Create clinic with owner
        self.clinic = Clinic.objects.create(
            name="Test Clinic",
            cnpj="12345678000190",
            owner=self.owner
        )
        
        # Create clinic admin
        self.admin = User.objects.create_user(
            email="admin@test.com",
            cognito_sub="admin-sub",
            first_name="Admin",
            last_name="User",
            role='CLINIC_ADMIN',
            clinic=self.clinic
        )
        
        # Create clinic doctor
        self.doctor = User.objects.create_user(
            email="doctor@test.com",
            cognito_sub="doctor-sub",
            first_name="Dr.",
            last_name="Medico",
            role='CLINIC_DOCTOR',
            clinic=self.clinic
        )
        
        # Create individual doctor
        self.individual = User.objects.create_user(
            email="individual@test.com",
            cognito_sub="individual-sub",
            first_name="Dr.",
            last_name="Independente",
            role='INDIVIDUAL'
        )
    
    def test_clinic_admin(self):
        """Test clinic admin user."""
        self.assertTrue(self.admin.is_clinic_admin())
        self.assertFalse(self.admin.is_individual_doctor())
        self.assertEqual(self.admin.clinic, self.clinic)
    
    def test_clinic_doctor(self):
        """Test clinic doctor user."""
        self.assertTrue(self.doctor.is_clinic_doctor())
        self.assertFalse(self.doctor.is_individual_doctor())
        self.assertEqual(self.doctor.clinic, self.clinic)
    
    def test_individual_doctor(self):
        """Test individual doctor user."""
        self.assertTrue(self.individual.is_individual_doctor())
        self.assertFalse(self.individual.is_clinic_admin())
        self.assertIsNone(self.individual.clinic)
    
    def test_user_full_name(self):
        """Test user full name."""
        self.assertEqual(self.doctor.get_full_name(), "Dr. Medico")
        self.assertEqual(self.individual.get_full_name(), "Dr. Independente")