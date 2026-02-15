"""
Views for tenants app.
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import timedelta
from .models import Clinic, DoctorInvitation
from .serializers import ClinicSerializer, DoctorInvitationSerializer, DoctorInvitationCreateSerializer
from apps.accounts.models import User
from apps.accounts.permissions import IsClinicAdmin, TenantQuerySetMixin
from apps.audit.services import AuditService
import logging

logger = logging.getLogger(__name__)


class ClinicViewSet(viewsets.ModelViewSet):
    """ViewSet for Clinic model."""
    
    queryset = Clinic.objects.all()
    serializer_class = ClinicSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter clinics by user."""
        user = self.request.user
        if user.clinic:
            return Clinic.objects.filter(id=user.clinic.id)
        if user.is_staff:
            return Clinic.objects.all()
        return Clinic.objects.none()
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsClinicAdmin])
    def invite(self, request):
        """
        Invite a doctor to the clinic.
        """
        serializer = DoctorInvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        clinic = request.user.clinic
        if not clinic:
            return Response(
                {'error': 'User must belong to a clinic'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check seat limit
        from django.conf import settings
        if settings.ENABLE_SEAT_LIMIT_CHECK and not clinic.can_add_doctor():
            return Response(
                {'error': 'Clinic has reached seat limit'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            email = serializer.validated_data['email']
            
            # Check if invitation already exists
            existing = DoctorInvitation.objects.filter(
                clinic=clinic,
                email=email,
                status='PENDING'
            ).first()
            
            if existing:
                return Response(
                    {'error': 'Invitation already sent to this email'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create invitation
            invitation = DoctorInvitation.objects.create(
                clinic=clinic,
                email=email,
                invited_by=request.user,
                expires_at=timezone.now() + timedelta(days=7)
            )
            
            # Log audit
            AuditService.log_doctor_invite(clinic, request.user, email)
            
            response_serializer = DoctorInvitationSerializer(invitation)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            logger.error(f"Failed to invite doctor: {e}")
            return Response(
                {'error': 'Failed to send invitation'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsClinicAdmin])
    def doctors(self, request):
        """
        List doctors in the clinic.
        """
        clinic = request.user.clinic
        if not clinic:
            return Response(
                {'error': 'User must belong to a clinic'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        doctors = clinic.doctors.filter(is_active=True)
        from apps.accounts.serializers import UserSerializer
        serializer = UserSerializer(doctors, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['delete'], permission_classes=[IsAuthenticated, IsClinicAdmin])
    def remove_doctor(self, request):
        """
        Remove a doctor from the clinic.
        """
        clinic = request.user.clinic
        if not clinic:
            return Response(
                {'error': 'User must belong to a clinic'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        doctor_id = request.query_params.get('doctor_id')
        if not doctor_id:
            return Response(
                {'error': 'doctor_id parameter required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            doctor = User.objects.get(id=doctor_id, clinic=clinic)
            doctor.is_active = False
            doctor.save()
            
            # Log audit
            AuditService.log_doctor_remove(clinic, request.user, doctor)
            
            return Response({'status': 'Doctor removed'}, status=status.HTTP_200_OK)
        
        except User.DoesNotExist:
            return Response(
                {'error': 'Doctor not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Failed to remove doctor: {e}")
            return Response(
                {'error': 'Failed to remove doctor'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DoctorInvitationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for DoctorInvitation model."""
    
    queryset = DoctorInvitation.objects.all()
    serializer_class = DoctorInvitationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter invitations by clinic."""
        user = self.request.user
        if user.clinic:
            return DoctorInvitation.objects.filter(clinic=user.clinic)
        return DoctorInvitation.objects.none()
