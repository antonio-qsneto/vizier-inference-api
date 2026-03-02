"""
Email helpers for clinic invitation workflows.
"""

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import DoctorInvitation


def send_doctor_invitation_email(invitation: DoctorInvitation) -> None:
    """
    Send an email informing the invited doctor about the invitation and login URL.
    """
    inviter_name = invitation.invited_by.get_full_name() if invitation.invited_by else "Administrador da clinica"
    inviter_email = invitation.invited_by.email if invitation.invited_by else "Administrador da clinica"
    platform_name = settings.INVITATION_PLATFORM_NAME
    login_url = settings.INVITATION_LOGIN_URL
    expires_at = timezone.localtime(invitation.expires_at).strftime("%Y-%m-%d %H:%M %Z")

    subject = f"{platform_name}: convite para acessar a clinica {invitation.clinic.name}"
    message = (
        f"Ola,\n\n"
        f"{inviter_name} convidou voce para acessar a clinica \"{invitation.clinic.name}\" no {platform_name}.\n\n"
        f"Para entrar, acesse: {login_url}\n\n"
        f"E-mail convidado: {invitation.email}\n"
        f"Convite enviado por: {inviter_email}\n"
        f"Convite valido ate: {expires_at}\n\n"
        f"Se voce ainda nao possui conta, crie seu cadastro usando este mesmo e-mail e depois faca login para aceitar o convite.\n\n"
        f"Se voce nao esperava este convite, pode ignorar esta mensagem."
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[invitation.email],
        fail_silently=False,
    )
