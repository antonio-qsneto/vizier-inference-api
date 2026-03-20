"""URLs for async inference control plane."""

from django.urls import path

from .views import (
    InferenceJobCreateView,
    InferenceJobDeleteView,
    InferenceJobOutputsView,
    InferenceJobStatusView,
    InferenceJobUploadCompleteView,
    InferenceOutputPresignDownloadView,
)

urlpatterns = [
    path("jobs/", InferenceJobCreateView.as_view(), name="inference-job-create"),
    path("jobs/<uuid:job_id>/", InferenceJobDeleteView.as_view(), name="inference-job-delete"),
    path("jobs/<uuid:job_id>/upload-complete/", InferenceJobUploadCompleteView.as_view(), name="inference-job-upload-complete"),
    path("jobs/<uuid:job_id>/status/", InferenceJobStatusView.as_view(), name="inference-job-status"),
    path("jobs/<uuid:job_id>/outputs/", InferenceJobOutputsView.as_view(), name="inference-job-outputs"),
    path(
        "jobs/<uuid:job_id>/outputs/<uuid:output_id>/presign-download/",
        InferenceOutputPresignDownloadView.as_view(),
        name="inference-output-presign-download",
    ),
]
