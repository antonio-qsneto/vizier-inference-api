"""Serializers for async inference control plane endpoints."""

from __future__ import annotations

from rest_framework import serializers

from .models import InferenceJob, InputArtifact, OutputArtifact


ALLOWED_UPLOAD_EXTENSIONS = (".zip", ".npz", ".nii", ".nii.gz")


class InferenceJobCreateRequestSerializer(serializers.Serializer):
    file_name = serializers.CharField(max_length=512)
    file_size = serializers.IntegerField(min_value=1, required=False)
    content_type = serializers.CharField(max_length=255, required=False, allow_blank=True)

    case_identification = serializers.CharField(max_length=255, required=False, allow_blank=True)
    patient_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    age = serializers.IntegerField(min_value=0, max_value=130, required=False)
    exam_source = serializers.CharField(max_length=255, required=False, allow_blank=True)
    exam_modality = serializers.CharField(max_length=100, required=False, allow_blank=True)
    category_id = serializers.CharField(max_length=255, required=False, allow_blank=True)

    requested_model = serializers.CharField(max_length=128, required=False, allow_blank=True)
    requested_model_version = serializers.CharField(max_length=64, required=False, allow_blank=True)
    requested_device = serializers.ChoiceField(
        choices=["cuda", "cpu"],
        required=False,
        default="cuda",
    )
    slice_batch_size = serializers.IntegerField(min_value=1, max_value=64, required=False)
    correlation_id = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_file_name(self, value: str) -> str:
        lowered = value.lower().strip()
        if not lowered.endswith(ALLOWED_UPLOAD_EXTENSIONS):
            raise serializers.ValidationError(
                "Unsupported file extension. Allowed: .zip, .npz, .nii, .nii.gz"
            )
        return value.strip()

    def validate_content_type(self, value: str) -> str:
        return value.strip() or "application/octet-stream"


class InputArtifactUploadCompleteSerializer(serializers.Serializer):
    input_artifact_id = serializers.UUIDField(required=False)
    key = serializers.CharField(max_length=1024, required=False, allow_blank=False)
    etag = serializers.CharField(max_length=128, required=False, allow_blank=True)
    size_bytes = serializers.IntegerField(required=False, min_value=1)


class InputArtifactSerializer(serializers.ModelSerializer):
    class Meta:
        model = InputArtifact
        fields = [
            "id",
            "job",
            "bucket",
            "key",
            "kind",
            "original_filename",
            "content_type",
            "size_bytes",
            "etag",
            "upload_status",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class OutputArtifactSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutputArtifact
        fields = [
            "id",
            "job",
            "bucket",
            "key",
            "kind",
            "content_type",
            "size_bytes",
            "etag",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields


class InferenceJobStatusSerializer(serializers.ModelSerializer):
    input_artifacts = InputArtifactSerializer(many=True, read_only=True)

    class Meta:
        model = InferenceJob
        fields = [
            "id",
            "tenant",
            "owner",
            "study",
            "request_payload",
            "status",
            "progress_percent",
            "requested_device",
            "slice_batch_size",
            "gpu_task_arn",
            "attempt_count",
            "correlation_id",
            "idempotency_key",
            "error_type",
            "error_message",
            "created_at",
            "updated_at",
            "uploaded_at",
            "started_at",
            "completed_at",
            "input_artifacts",
        ]
        read_only_fields = fields


class InferenceJobCreateResponseSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    status = serializers.CharField()
    tenant_id = serializers.UUIDField()
    correlation_id = serializers.CharField()
    upload = serializers.DictField()


class InferenceJobListItemSerializer(serializers.ModelSerializer):
    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    request_payload = serializers.JSONField()

    class Meta:
        model = InferenceJob
        fields = [
            "id",
            "status",
            "progress_percent",
            "error_type",
            "error_message",
            "created_at",
            "updated_at",
            "completed_at",
            "correlation_id",
            "request_payload",
            "owner_email",
        ]
        read_only_fields = fields


class OutputPresignDownloadResponseSerializer(serializers.Serializer):
    output_id = serializers.UUIDField()
    kind = serializers.CharField()
    url = serializers.CharField()
    expires_in = serializers.IntegerField()


class InferenceJobOutputsResponseSerializer(serializers.Serializer):
    job_id = serializers.UUIDField()
    status = serializers.CharField()
    outputs = OutputArtifactSerializer(many=True)


class InferenceJobListResponseSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    results = InferenceJobListItemSerializer(many=True)
