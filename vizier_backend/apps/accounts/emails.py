"""
Email helpers for public contact/consultation requests.
"""

from django.conf import settings
from django.core.mail import send_mail


CONSULTATION_RECIPIENTS = ["vizier.med@gmail.com"]


def _value_or_default(value: str | None) -> str:
    normalized = (value or "").strip()
    return normalized if normalized else "Não informado"


def send_consultation_request_email(payload: dict) -> None:
    """
    Send a lead notification for "Solicite uma consulta" submissions.
    """
    subject = "[Vizier] Nova solicitação de consulta"

    message = (
        "Nova solicitação de consulta recebida pelo site.\n\n"
        f"Nome: {_value_or_default(payload.get('first_name'))}\n"
        f"Sobrenome: {_value_or_default(payload.get('last_name'))}\n"
        f"Nome da empresa: {_value_or_default(payload.get('company_name'))}\n"
        f"Cargo: {_value_or_default(payload.get('job_title'))}\n"
        f"Seu e-mail: {_value_or_default(payload.get('email'))}\n"
        f"País: {_value_or_default(payload.get('country'))}\n"
        f"Mensagem: {_value_or_default(payload.get('message'))}\n"
        "Como você ficou sabendo de nós?: "
        f"{_value_or_default(payload.get('discovery_source'))}\n"
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=CONSULTATION_RECIPIENTS,
        fail_silently=False,
    )
