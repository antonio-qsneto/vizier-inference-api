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

    def create(self, request, *args, **kwargs):
        """
        Create a clinic and attach the requesting user as its owner/admin.

        Notes:
        - Clinic.owner is required, so we always set it from request.user.
        - Users can belong to only one clinic; this endpoint is for onboarding.
        """
        if request.user.clinic_id:
            return Response(
                {'error': 'User already belongs to a clinic'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if Clinic.objects.filter(owner=request.user).exists():
            return Response(
                {'error': 'User already owns a clinic'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        clinic = serializer.save(owner=request.user)

        request.user.clinic = clinic
        request.user.role = 'CLINIC_ADMIN'
        request.user.save(update_fields=['clinic', 'role', 'updated_at'])

        AuditService.log_action(
            clinic=clinic,
            action='CLINIC_CREATED',
            user=request.user,
            resource_id=str(clinic.id),
            details={'name': clinic.name},
        )

        response_serializer = self.get_serializer(clinic)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
    
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

            # If the user is already an active clinic doctor, don't invite again.
            if User.objects.filter(
                clinic=clinic,
                email=email,
                role='CLINIC_DOCTOR',
                is_active=True,
            ).exists():
                return Response(
                    {'error': 'User is already a doctor in this clinic'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            invitation, created = DoctorInvitation.objects.get_or_create(
                clinic=clinic,
                email=email,
                defaults={
                    'invited_by': request.user,
                    'expires_at': timezone.now() + timedelta(days=7),
                },
            )

            if not created:
                if invitation.status == 'PENDING' and not invitation.is_expired():
                    return Response(
                        {'error': 'Invitation already sent to this email'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                invitation.status = 'PENDING'
                invitation.invited_by = request.user
                invitation.expires_at = timezone.now() + timedelta(days=7)
                invitation.accepted_at = None
                invitation.save(
                    update_fields=['status', 'invited_by', 'expires_at', 'accepted_at']
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
        
        doctors = clinic.doctors.filter(is_active=True, role='CLINIC_DOCTOR')
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
            doctor = User.objects.get(
                id=doctor_id,
                clinic=clinic,
                role='CLINIC_DOCTOR',
            )
            DoctorInvitation.objects.filter(
                clinic=clinic,
                email=doctor.email,
                status='ACCEPTED',
            ).update(status='REMOVED')
            doctor.clinic = None
            doctor.role = 'INDIVIDUAL'
            doctor.save(update_fields=['clinic', 'role', 'updated_at'])
            
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
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my_invitations(self, request):
        """
        Get all pending invitations for the current user's email.
        """
        email = request.user.email
        invitations = DoctorInvitation.objects.filter(
            email=email,
            status='PENDING'
        )
        
        # Check if any invitation is expired
        for inv in invitations:
            if inv.is_expired():
                inv.status = 'EXPIRED'
                inv.save()
        
        # Re-fetch non-expired invitations
        invitations = invitations.filter(status='PENDING')
        serializer = self.get_serializer(invitations, many=True)
        return Response(serializer.data)
    
    @action(detail='uuid', methods=['post'], permission_classes=[IsAuthenticated])
    def accept(self, request, pk=None):
        """
        Accept a doctor invitation.
        Updates user role to CLINIC_DOCTOR and links to clinic.
        """
        try:
            invitation = DoctorInvitation.objects.get(id=pk)
        except DoctorInvitation.DoesNotExist:
            return Response(
                {'error': 'Invitation not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Validate invitation
        if invitation.email != request.user.email:
            return Response(
                {'error': 'Invitation is for a different email'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if invitation.status != 'PENDING':
            return Response(
                {'error': f'Invitation is already {invitation.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if invitation.is_expired():
            invitation.status = 'EXPIRED'
            invitation.save()
            return Response(
                {'error': 'Invitation has expired'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user already belongs to a clinic
        if request.user.clinic and request.user.clinic != invitation.clinic:
            return Response(
                {'error': 'User already belongs to another clinic'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Accept invitation
            invitation.accept()
            
            # Update user
            request.user.clinic = invitation.clinic
            request.user.role = 'CLINIC_DOCTOR'
            request.user.save(update_fields=['clinic', 'role', 'updated_at'])
            
            # Log audit
            AuditService.log_action(
                clinic=invitation.clinic,
                action='DOCTOR_ACCEPTED_INVITE',
                user=request.user,
                resource_id=str(invitation.id),
                details={'doctor_email': request.user.email}
            )
            
            response_serializer = self.get_serializer(invitation)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Failed to accept invitation: {e}")
            return Response(
                {'error': 'Failed to accept invitation'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
