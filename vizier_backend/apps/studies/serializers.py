"""
Serializers for studies app.
"""

from rest_framework import serializers
from .models import Study, Job


class JobSerializer(serializers.ModelSerializer):
    """Serializer for Job model."""
    
    class Meta:
        model = Job
        fields = [
            'id',
            'external_job_id',
            'status',
            'progress_percent',
            'created_at',
            'started_at',
            'completed_at',
        ]
        read_only_fields = fields


class StudySerializer(serializers.ModelSerializer):
    """Serializer for Study model."""
    
    job = JobSerializer(read_only=True)
    owner_email = serializers.CharField(source='owner.email', read_only=True)
    
    class Meta:
        model = Study
        fields = [
            'id',
            'category',
            'status',
            'owner_email',
            'job',
            's3_key',
            'image_s3_key',
            'mask_s3_key',
            'error_message',
            'created_at',
            'updated_at',
            'completed_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'job',
            's3_key',
            'image_s3_key',
            'mask_s3_key',
            'error_message',
            'created_at',
            'updated_at',
            'completed_at',
        ]


class StudyCreateSerializer(serializers.Serializer):
    """Serializer for creating studies."""
    
    dicom_zip = serializers.FileField(required=False)
    npz_file = serializers.FileField(required=False)
    file = serializers.FileField(required=False)  # backward-compat alias
    category_id = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs):
        upload = attrs.get('dicom_zip') or attrs.get('npz_file') or attrs.get('file')
        if not upload:
            raise serializers.ValidationError(
                "Provide a file using 'dicom_zip' (.zip) or 'npz_file' (.npz)."
            )

        name = (getattr(upload, 'name', '') or '').lower()
        if name.endswith('.zip'):
            attrs['upload_type'] = 'zip'
        elif name.endswith('.npz'):
            attrs['upload_type'] = 'npz'
        else:
            raise serializers.ValidationError("File must be a ZIP (.zip) or NPZ (.npz).")

        attrs['upload_file'] = upload
        return attrs


class StudyStatusSerializer(serializers.ModelSerializer):
    """Serializer for study status."""
    
    job_status = serializers.CharField(source='job.status', read_only=True)
    job_progress = serializers.IntegerField(source='job.progress_percent', read_only=True)
    
    class Meta:
        model = Study
        fields = [
            'id',
            'status',
            'job_status',
            'job_progress',
            'updated_at',
        ]
        read_only_fields = fields


class StudyResultSerializer(serializers.Serializer):
    """Serializer for study visualization assets (signed URLs)."""
    
    study_id = serializers.CharField()
    image_url = serializers.CharField()
    mask_url = serializers.CharField()
    expires_in = serializers.IntegerField()
    image_file_name = serializers.CharField()
    mask_file_name = serializers.CharField()
