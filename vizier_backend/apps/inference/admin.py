from django.contrib import admin

from .models import (
    AuditEvent,
    InferenceJob,
    InputArtifact,
    JobStatusHistory,
    ModelVersion,
    OutputArtifact,
    Tenant,
)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "clinic", "owner_user", "is_active", "created_at")
    list_filter = ("type", "is_active")
    search_fields = ("id", "clinic__name", "owner_user__email")


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "executor", "is_active", "updated_at")
    list_filter = ("executor", "is_active")
    search_fields = ("name", "version")


@admin.register(InferenceJob)
class InferenceJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "tenant",
        "owner",
        "status",
        "progress_percent",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "tenant__type")
    search_fields = ("id", "correlation_id", "idempotency_key", "owner__email")


@admin.register(InputArtifact)
class InputArtifactAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "kind", "upload_status", "bucket", "key", "size_bytes")
    list_filter = ("kind", "upload_status")
    search_fields = ("job__id", "key", "bucket", "etag")


@admin.register(OutputArtifact)
class OutputArtifactAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "kind", "bucket", "key", "size_bytes", "created_at")
    list_filter = ("kind",)
    search_fields = ("job__id", "key", "bucket", "etag")


@admin.register(JobStatusHistory)
class JobStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "from_status", "to_status", "actor_user", "created_at")
    list_filter = ("to_status",)
    search_fields = ("job__id", "reason")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "action", "job", "user", "timestamp")
    list_filter = ("action",)
    search_fields = ("correlation_id", "job__id", "tenant__id")
