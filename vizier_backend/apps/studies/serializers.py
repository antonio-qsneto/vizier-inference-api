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
            'case_identification',
            'patient_name',
            'age',
            'exam_source',
            'exam_modality',
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
    nifti_file = serializers.FileField(required=False)
    file = serializers.FileField(required=False)  # backward-compat alias
    case_identification = serializers.CharField(max_length=255)
    patient_name = serializers.CharField(max_length=255)
    age = serializers.IntegerField(min_value=0, max_value=130)
    exam_source = serializers.CharField(max_length=255)
    exam_modality = serializers.CharField(max_length=100)
    category_id = serializers.CharField(max_length=255)

    def validate(self, attrs):
        errors = {}
        upload = attrs.get('dicom_zip') or attrs.get('npz_file') or attrs.get('nifti_file') or attrs.get('file')
        if not upload:
            received_file_like_keys = sorted(
                key
                for key in getattr(self, 'initial_data', {}).keys()
                if (
                    'file' in str(key).lower()
                    or 'zip' in str(key).lower()
                    or 'nii' in str(key).lower()
                    or 'nifti' in str(key).lower()
                )
            )
            expected_keys = "'file', 'dicom_zip', 'npz_file', 'nifti_file'"
            if received_file_like_keys:
                errors['file'] = (
                    f"Upload field not recognized. Use one of {expected_keys}. "
                    f"Received file-like keys: {', '.join(received_file_like_keys)}."
                )
            else:
                errors['file'] = (
                    f"Missing upload file. Send one of {expected_keys} "
                    "with extensions .zip, .npz, .nii or .nii.gz."
                )

        for field_name in ['case_identification', 'patient_name', 'exam_source', 'exam_modality', 'category_id']:
            value = attrs.get(field_name)
            if isinstance(value, str):
                cleaned = value.strip()
                if not cleaned:
                    errors[field_name] = 'This field may not be blank.'
                attrs[field_name] = cleaned

        if upload:
            name = (getattr(upload, 'name', '') or '').lower()
            if name.endswith('.zip'):
                attrs['upload_type'] = 'zip'
            elif name.endswith('.npz'):
                attrs['upload_type'] = 'npz'
            elif name.endswith('.nii') or name.endswith('.nii.gz'):
                attrs['upload_type'] = 'nifti'
            else:
                errors['file'] = "Invalid extension. File must be ZIP (.zip), NPZ (.npz), or NIfTI (.nii/.nii.gz)."

        if errors:
            raise serializers.ValidationError(errors)

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
    segments_legend = serializers.ListField(child=serializers.DictField(), required=False)
    expires_in = serializers.IntegerField()
    image_file_name = serializers.CharField()
    mask_file_name = serializers.CharField()
