#!/bin/sh

# Create the dedicated application bucket if absent. This script must never
# enumerate, delete, or alter other buckets or objects.
set -eu

: "${MINIO_ROOT_USER:?Set MINIO_ROOT_USER before enabling the education-storage profile}"
: "${MINIO_ROOT_PASSWORD:?Set MINIO_ROOT_PASSWORD before enabling the education-storage profile}"

attempt=0
until mc alias set education "$MINIO_ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "MinIO did not become ready for education bucket initialization" >&2
    exit 1
  fi
  sleep 1
done

mc mb --ignore-existing "education/$EDUCATION_ASSET_BUCKET" >/dev/null
