#!/bin/sh

# Create the dedicated application bucket if absent and allow anonymous reads
# only for avatar objects. This script must never enumerate, delete, or alter
# other buckets or objects.
set -eu

: "${MINIO_ROOT_USER:?Set MINIO_ROOT_USER before enabling the education-storage profile}"
: "${MINIO_ROOT_PASSWORD:?Set MINIO_ROOT_PASSWORD before enabling the education-storage profile}"
: "${STORAGE_BUCKET_NAME:?Set STORAGE_BUCKET_NAME before enabling the education-storage profile}"

attempt=0
until mc alias set education "$MINIO_ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "MinIO did not become ready for education bucket initialization" >&2
    exit 1
  fi
  sleep 1
done

mc mb --ignore-existing "education/$STORAGE_BUCKET_NAME" >/dev/null

cat > /tmp/langalpha-avatar-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"AWS": ["*"]},
      "Action": ["s3:GetObject"],
      "Resource": ["arn:aws:s3:::$STORAGE_BUCKET_NAME/avatars/*"]
    }
  ]
}
EOF

mc anonymous set-json /tmp/langalpha-avatar-policy.json "education/$STORAGE_BUCKET_NAME" >/dev/null
rm -f /tmp/langalpha-avatar-policy.json
