#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?AWS_REGION is required}"
: "${SOURCE_TAG:?SOURCE_TAG is required}"
: "${TARGET_TAG:?TARGET_TAG is required}"

if [[ -z "${ECR_REPOSITORY:-}" && -z "${ECR_REPOSITORY_URI:-}" ]]; then
  echo "ECR_REPOSITORY or ECR_REPOSITORY_URI is required"
  exit 1
fi

if [[ -n "${ECR_REPOSITORY_URI:-}" ]]; then
  REPOSITORY_NAME="${ECR_REPOSITORY_URI##*/}"
else
  REPOSITORY_NAME="${ECR_REPOSITORY}"
fi

if [[ "${SOURCE_TAG}" == "${TARGET_TAG}" ]]; then
  echo "SOURCE_TAG and TARGET_TAG are equal (${SOURCE_TAG}); nothing to do."
  exit 0
fi

echo "Promoting image tag in ${REPOSITORY_NAME}: ${SOURCE_TAG} -> ${TARGET_TAG}"

MANIFEST="$(aws ecr batch-get-image \
  --region "${AWS_REGION}" \
  --repository-name "${REPOSITORY_NAME}" \
  --image-ids "imageTag=${SOURCE_TAG}" \
  --query 'images[0].imageManifest' \
  --output text)"

if [[ -z "${MANIFEST}" || "${MANIFEST}" == "None" ]]; then
  echo "Source image tag not found: ${SOURCE_TAG}"
  exit 1
fi

aws ecr put-image \
  --region "${AWS_REGION}" \
  --repository-name "${REPOSITORY_NAME}" \
  --image-tag "${TARGET_TAG}" \
  --image-manifest "${MANIFEST}" >/dev/null

echo "Tag promotion completed."
