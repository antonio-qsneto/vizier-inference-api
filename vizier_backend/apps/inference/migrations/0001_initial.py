# Generated manually for async inference domain.

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("studies", "0005_study_descriptive_analysis"),
        ("tenants", "0006_clinic_cancel_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ModelVersion",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("name", models.CharField(max_length=128)),
                ("version", models.CharField(max_length=64)),
                ("executor", models.CharField(max_length=64, default="biomedparse")),
                ("metadata", models.JSONField(default=dict, blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "inference_model_version",
            },
        ),
        migrations.CreateModel(
            name="Tenant",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                (
                    "type",
                    models.CharField(
                        max_length=16,
                        choices=[("CLINIC", "Clinic"), ("INDIVIDUAL", "Individual")],
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "clinic",
                    models.ForeignKey(
                        to="tenants.clinic",
                        on_delete=django.db.models.deletion.CASCADE,
                        null=True,
                        blank=True,
                        related_name="inference_tenants",
                    ),
                ),
                (
                    "owner_user",
                    models.ForeignKey(
                        to=settings.AUTH_USER_MODEL,
                        on_delete=django.db.models.deletion.CASCADE,
                        null=True,
                        blank=True,
                        related_name="owned_inference_tenants",
                    ),
                ),
            ],
            options={
                "db_table": "inference_tenant",
            },
        ),
        migrations.CreateModel(
            name="InferenceJob",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                (
                    "status",
                    models.CharField(
                        max_length=32,
                        default="CREATED",
                        choices=[
                            ("CREATED", "Created"),
                            ("UPLOAD_PENDING", "Upload pending"),
                            ("UPLOADED", "Uploaded"),
                            ("VALIDATING", "Validating"),
                            ("PREPROCESSING", "Preprocessing"),
                            ("QUEUED", "Queued"),
                            ("RUNNING", "Running"),
                            ("POSTPROCESSING", "Postprocessing"),
                            ("COMPLETED", "Completed"),
                            ("FAILED", "Failed"),
                        ],
                    ),
                ),
                ("progress_percent", models.PositiveSmallIntegerField(default=0)),
                ("idempotency_key", models.CharField(max_length=255, null=True, blank=True)),
                ("correlation_id", models.CharField(max_length=255, db_index=True)),
                ("request_payload", models.JSONField(default=dict, blank=True)),
                ("error_type", models.CharField(max_length=128, null=True, blank=True)),
                ("error_message", models.TextField(null=True, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("uploaded_at", models.DateTimeField(null=True, blank=True)),
                ("started_at", models.DateTimeField(null=True, blank=True)),
                ("completed_at", models.DateTimeField(null=True, blank=True)),
                (
                    "owner",
                    models.ForeignKey(
                        to=settings.AUTH_USER_MODEL,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inference_jobs",
                    ),
                ),
                (
                    "requested_model_version",
                    models.ForeignKey(
                        to="inference.modelversion",
                        on_delete=django.db.models.deletion.SET_NULL,
                        null=True,
                        blank=True,
                        related_name="jobs",
                    ),
                ),
                (
                    "study",
                    models.ForeignKey(
                        to="studies.study",
                        on_delete=django.db.models.deletion.SET_NULL,
                        null=True,
                        blank=True,
                        related_name="inference_jobs",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        to="inference.tenant",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="jobs",
                    ),
                ),
            ],
            options={
                "db_table": "inference_job",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="InputArtifact",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("bucket", models.CharField(max_length=255)),
                ("key", models.CharField(max_length=1024)),
                (
                    "kind",
                    models.CharField(
                        max_length=32,
                        choices=[("RAW_UPLOAD", "Raw upload"), ("NORMALIZED_INPUT", "Normalized input")],
                    ),
                ),
                ("original_filename", models.CharField(max_length=512, null=True, blank=True)),
                ("content_type", models.CharField(max_length=255, null=True, blank=True)),
                ("size_bytes", models.BigIntegerField(null=True, blank=True)),
                ("etag", models.CharField(max_length=128, null=True, blank=True)),
                ("checksum_sha256", models.CharField(max_length=128, null=True, blank=True)),
                (
                    "upload_status",
                    models.CharField(
                        max_length=32,
                        default="PENDING",
                        choices=[
                            ("PENDING", "Pending"),
                            ("UPLOADED", "Uploaded"),
                            ("VALIDATED", "Validated"),
                        ],
                    ),
                ),
                ("metadata", models.JSONField(default=dict, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "job",
                    models.ForeignKey(
                        to="inference.inferencejob",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="input_artifacts",
                    ),
                ),
            ],
            options={
                "db_table": "inference_input_artifact",
            },
        ),
        migrations.CreateModel(
            name="OutputArtifact",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("bucket", models.CharField(max_length=255)),
                ("key", models.CharField(max_length=1024)),
                (
                    "kind",
                    models.CharField(
                        max_length=64,
                        choices=[
                            ("NORMALIZED_INPUT_NPZ", "Normalized input NPZ"),
                            ("ORIGINAL_NIFTI", "Original NIfTI"),
                            ("MASK_NIFTI", "Mask NIfTI"),
                            ("SUMMARY_JSON", "Summary JSON"),
                            ("EXTRA", "Extra artifact"),
                        ],
                    ),
                ),
                ("content_type", models.CharField(max_length=255, null=True, blank=True)),
                ("size_bytes", models.BigIntegerField(null=True, blank=True)),
                ("etag", models.CharField(max_length=128, null=True, blank=True)),
                ("metadata", models.JSONField(default=dict, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "job",
                    models.ForeignKey(
                        to="inference.inferencejob",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="output_artifacts",
                    ),
                ),
            ],
            options={
                "db_table": "inference_output_artifact",
            },
        ),
        migrations.CreateModel(
            name="JobStatusHistory",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("from_status", models.CharField(max_length=32, null=True, blank=True)),
                ("to_status", models.CharField(max_length=32)),
                ("reason", models.CharField(max_length=255, null=True, blank=True)),
                ("metadata", models.JSONField(default=dict, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor_user",
                    models.ForeignKey(
                        to=settings.AUTH_USER_MODEL,
                        on_delete=django.db.models.deletion.SET_NULL,
                        null=True,
                        blank=True,
                        related_name="inference_status_history_events",
                    ),
                ),
                (
                    "job",
                    models.ForeignKey(
                        to="inference.inferencejob",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_history",
                    ),
                ),
            ],
            options={
                "db_table": "inference_job_status_history",
            },
        ),
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("action", models.CharField(max_length=64)),
                ("correlation_id", models.CharField(max_length=255, null=True, blank=True)),
                ("payload", models.JSONField(default=dict, blank=True)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                (
                    "job",
                    models.ForeignKey(
                        to="inference.inferencejob",
                        on_delete=django.db.models.deletion.SET_NULL,
                        null=True,
                        blank=True,
                        related_name="audit_events",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        to="inference.tenant",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_events",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        to=settings.AUTH_USER_MODEL,
                        on_delete=django.db.models.deletion.SET_NULL,
                        null=True,
                        blank=True,
                        related_name="inference_audit_events",
                    ),
                ),
            ],
            options={
                "db_table": "inference_audit_event",
            },
        ),
        migrations.AddIndex(
            model_name="modelversion",
            index=models.Index(fields=["name", "version"], name="inference_m_name_86eef8_idx"),
        ),
        migrations.AddIndex(
            model_name="modelversion",
            index=models.Index(fields=["executor", "is_active"], name="inference_m_execute_ced96d_idx"),
        ),
        migrations.AddConstraint(
            model_name="modelversion",
            constraint=models.UniqueConstraint(fields=["name", "version"], name="inference_model_version_unique_name_version"),
        ),
        migrations.AddIndex(
            model_name="tenant",
            index=models.Index(fields=["type", "is_active"], name="inference_t_type_ae1f76_idx"),
        ),
        migrations.AddIndex(
            model_name="tenant",
            index=models.Index(fields=["clinic"], name="inference_t_clinic__9cf037_idx"),
        ),
        migrations.AddIndex(
            model_name="tenant",
            index=models.Index(fields=["owner_user"], name="inference_t_owner_u_85f3b6_idx"),
        ),
        migrations.AddConstraint(
            model_name="tenant",
            constraint=models.CheckConstraint(
                check=(
                    (models.Q(("type", "CLINIC"), ("clinic__isnull", False), ("owner_user__isnull", True)))
                    | (models.Q(("type", "INDIVIDUAL"), ("owner_user__isnull", False), ("clinic__isnull", True)))
                ),
                name="inference_tenant_shape_constraint",
            ),
        ),
        migrations.AddConstraint(
            model_name="tenant",
            constraint=models.UniqueConstraint(fields=["clinic"], condition=models.Q(("clinic__isnull", False)), name="inference_tenant_unique_clinic"),
        ),
        migrations.AddConstraint(
            model_name="tenant",
            constraint=models.UniqueConstraint(fields=["owner_user"], condition=models.Q(("owner_user__isnull", False)), name="inference_tenant_unique_owner_user"),
        ),
        migrations.AddIndex(
            model_name="inferencejob",
            index=models.Index(fields=["tenant", "created_at"], name="inference_j_tenant__eb9db6_idx"),
        ),
        migrations.AddIndex(
            model_name="inferencejob",
            index=models.Index(fields=["owner", "created_at"], name="inference_j_owner_i_9a67dd_idx"),
        ),
        migrations.AddIndex(
            model_name="inferencejob",
            index=models.Index(fields=["status", "updated_at"], name="inference_j_status_9fcf6c_idx"),
        ),
        migrations.AddIndex(
            model_name="inferencejob",
            index=models.Index(fields=["idempotency_key"], name="inference_j_idempot_8d4f66_idx"),
        ),
        migrations.AddConstraint(
            model_name="inferencejob",
            constraint=models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=models.Q(("idempotency_key__isnull", False)),
                name="inference_job_unique_tenant_idempotency",
            ),
        ),
        migrations.AddIndex(
            model_name="inputartifact",
            index=models.Index(fields=["job", "kind"], name="inference_i_job_id_31f080_idx"),
        ),
        migrations.AddIndex(
            model_name="inputartifact",
            index=models.Index(fields=["bucket", "key"], name="inference_i_bucket_14f507_idx"),
        ),
        migrations.AddIndex(
            model_name="inputartifact",
            index=models.Index(fields=["upload_status"], name="inference_i_upload__5e1551_idx"),
        ),
        migrations.AddConstraint(
            model_name="inputartifact",
            constraint=models.UniqueConstraint(fields=["job", "kind"], name="inference_input_artifact_unique_job_kind"),
        ),
        migrations.AddIndex(
            model_name="outputartifact",
            index=models.Index(fields=["job", "kind"], name="inference_o_job_id_2cdd14_idx"),
        ),
        migrations.AddIndex(
            model_name="outputartifact",
            index=models.Index(fields=["bucket", "key"], name="inference_o_bucket_1725c8_idx"),
        ),
        migrations.AddConstraint(
            model_name="outputartifact",
            constraint=models.UniqueConstraint(fields=["job", "kind"], name="inference_output_artifact_unique_job_kind"),
        ),
        migrations.AddIndex(
            model_name="jobstatushistory",
            index=models.Index(fields=["job", "created_at"], name="inference_j_job_id_74e1eb_idx"),
        ),
        migrations.AddIndex(
            model_name="jobstatushistory",
            index=models.Index(fields=["to_status", "created_at"], name="inference_j_to_stat_7b4b5a_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["tenant", "timestamp"], name="inference_a_tenant__59d917_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["job", "timestamp"], name="inference_a_job_id_f487bf_idx"),
        ),
        migrations.AddIndex(
            model_name="auditevent",
            index=models.Index(fields=["action", "timestamp"], name="inference_a_action_b096e7_idx"),
        ),
    ]
