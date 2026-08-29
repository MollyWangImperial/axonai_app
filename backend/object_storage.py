"""Optional Cloudflare R2 storage for assessment task videos.

The browser uploads directly with short-lived presigned URLs. Render stores
only object metadata and gives the trusted analysis worker a separate,
short-lived download URL when an assessment job is queued.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class R2Settings:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    endpoint_url: str
    region: str = "auto"

    @classmethod
    def from_environment(cls) -> "R2Settings | None":
        account_id = os.environ.get("R2_ACCOUNT_ID", "").strip()
        access_key_id = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
        secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
        bucket = os.environ.get("R2_BUCKET_NAME", "").strip()
        endpoint = os.environ.get("R2_ENDPOINT_URL", "").strip()
        if not endpoint and account_id:
            endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
        if not all((account_id, access_key_id, secret_access_key, bucket, endpoint)):
            return None
        return cls(account_id, access_key_id, secret_access_key, bucket, endpoint.rstrip("/"))


class TaskVideoObjectStorage:
    def __init__(self, settings: R2Settings | None = None) -> None:
        self.settings = settings or R2Settings.from_environment()
        self._client: Any = None

    @property
    def configured(self) -> bool:
        return self.settings is not None

    def _s3(self):
        if not self.settings:
            raise RuntimeError("Cloudflare R2 is not configured")
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=self.settings.endpoint_url,
                aws_access_key_id=self.settings.access_key_id,
                aws_secret_access_key=self.settings.secret_access_key,
                region_name=self.settings.region,
                config=Config(signature_version="s3v4"),
            )
        return self._client

    @staticmethod
    def user_prefix(user_id: str) -> str:
        digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:20]
        return f"patients/{digest}/assessment-videos"

    def object_key(
        self,
        user_id: str,
        package_id: str,
        task_id: str,
        video_id: str,
        extension: str,
    ) -> str:
        return f"{self.user_prefix(user_id)}/{package_id}/{task_id}/{video_id}.{extension}"

    def presign_put(self, key: str, content_type: str, expires_seconds: int = 900) -> str:
        return self._s3().generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.settings.bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_seconds,
        )

    def presign_get(self, key: str, expires_seconds: int = 900) -> str:
        return self._s3().generate_presigned_url(
            "get_object",
            Params={"Bucket": self.settings.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )

    def head(self, key: str) -> dict[str, Any]:
        return self._s3().head_object(Bucket=self.settings.bucket, Key=key)

    def delete(self, key: str) -> None:
        self._s3().delete_object(Bucket=self.settings.bucket, Key=key)


task_video_object_storage = TaskVideoObjectStorage()
