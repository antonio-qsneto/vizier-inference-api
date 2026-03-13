"""Bootstrap helper to initialize tenant/model version for first admin."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.inference.models import ModelVersion, Tenant


class Command(BaseCommand):
    help = "Create missing tenant + default model version for an initial admin user"

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Admin user email")
        parser.add_argument("--model-name", default="biomedparse")
        parser.add_argument("--model-version", default="v1")
        parser.add_argument(
            "--create-user-if-missing",
            action="store_true",
            help="Create a bootstrap user when email is not found",
        )
        parser.add_argument("--first-name", default="Bootstrap")
        parser.add_argument("--last-name", default="Admin")
        parser.add_argument(
            "--role",
            default="INDIVIDUAL",
            choices=["INDIVIDUAL", "CLINIC_ADMIN", "CLINIC_DOCTOR"],
        )
        parser.add_argument(
            "--make-superuser",
            action="store_true",
            help="Grant Django superuser/staff flags to the created bootstrap user",
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        model_name = options["model_name"].strip()
        model_version = options["model_version"].strip()
        create_user_if_missing = bool(options["create_user_if_missing"])
        first_name = options["first_name"].strip()
        last_name = options["last_name"].strip()
        role = options["role"].strip()
        make_superuser = bool(options["make_superuser"])

        User = get_user_model()
        user = User.objects.filter(email=email).first()
        if not user:
            if not create_user_if_missing:
                raise CommandError(f"User not found: {email}")

            user = User.objects.create_user(
                email=email,
                cognito_sub=f"bootstrap-{uuid.uuid4()}",
                first_name=first_name,
                last_name=last_name,
                role=role,
                is_active=True,
                is_staff=make_superuser,
                is_superuser=make_superuser,
            )
            self.stdout.write(self.style.WARNING(f"Created bootstrap user: {email}"))

        tenant = Tenant.resolve_for_user(user)
        model_obj, _ = ModelVersion.objects.get_or_create(
            name=model_name,
            version=model_version,
            defaults={
                "executor": "biomedparse",
                "is_active": True,
                "metadata": {},
            },
        )

        self.stdout.write(self.style.SUCCESS(f"Tenant ready: {tenant.id}"))
        self.stdout.write(self.style.SUCCESS(f"ModelVersion ready: {model_obj.name}:{model_obj.version}"))
