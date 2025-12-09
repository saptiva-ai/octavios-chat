from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional

from ports.storage_port import StorageMetadata, StoragePort

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:  # pragma: no cover - optional dependency fallback
    boto3 = None
    BotoCoreError = ClientError = Exception


class MinioStorageAdapter(StoragePort):
    """Storage adapter targeting MinIO/S3 with filesystem fallback."""

    def __init__(self):
        self.bucket = os.getenv("MINIO_BUCKET", "aletheia-artifacts")
        self.endpoint = os.getenv("MINIO_ENDPOINT")
        self.access_key = os.getenv("MINIO_ACCESS_KEY")
        self.secret_key = os.getenv("MINIO_SECRET_KEY")
        self.region = os.getenv("MINIO_REGION", "us-east-1")
        self.secure = os.getenv("MINIO_SECURE", "true").lower() == "true"
        self.verify_ssl = os.getenv("MINIO_VERIFY_SSL", "true").lower() == "true"

        self.mock_root = Path(os.getenv("LOCAL_STORAGE_ROOT", "./runs/storage"))
        self.mock_root.mkdir(parents=True, exist_ok=True)

        self.mock_mode = True
        self.s3_resource = None
        self.s3_client = None

        if all([self.endpoint, self.access_key, self.secret_key, boto3]):
            try:
                endpoint_url = self.endpoint
                if not endpoint_url.startswith(("http://", "https://")):
                    scheme = "https://" if self.secure else "http://"
                    endpoint_url = f"{scheme}{self.endpoint}"

                self.s3_resource = boto3.resource(
                    "s3",
                    endpoint_url=endpoint_url,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name=self.region,
                    use_ssl=self.secure,
                    verify=self.verify_ssl,
                )
                self.s3_client = self.s3_resource.meta.client
                self.mock_mode = False
                self._ensure_bucket_exists()
            except (ClientError, BotoCoreError) as exc:
                print(f"Warning: MinIO/S3 connection failed ({exc}). Falling back to local storage.")
                self.s3_resource = None
                self.s3_client = None
                self.mock_mode = True

    def store_object(self, key: str, data: bytes, metadata: Optional[Dict[str, Optional[str]]] = None) -> bool:
        metadata = self._clean_metadata(metadata)
        if self.mock_mode:
            return self._store_locally(key, data)

        try:
            self.s3_client.put_object(Bucket=self.bucket, Key=key, Body=data, Metadata=metadata)
            return True
        except (ClientError, BotoCoreError) as exc:
            print(f"Error storing object {key}: {exc}")
            return False

    def store_file(self, key: str, file_path: Path, metadata: Optional[Dict[str, Optional[str]]] = None) -> bool:
        file_path = Path(file_path)
        if not file_path.exists():
            print(f"File not found for storage: {file_path}")
            return False

        if self.mock_mode:
            return self._store_locally(key, file_path.read_bytes())

        try:
            with file_path.open("rb") as file_handle:
                self.s3_client.upload_fileobj(file_handle, self.bucket, key, ExtraArgs={"Metadata": self._clean_metadata(metadata)})
            return True
        except (ClientError, BotoCoreError) as exc:
            print(f"Error uploading file {file_path} to {key}: {exc}")
            return False

    def get_object(self, key: str) -> bytes | None:
        if self.mock_mode:
            path = self._local_path(key)
            return path.read_bytes() if path.exists() else None

        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except (ClientError, BotoCoreError):
            return None

    def get_object_stream(self, key: str) -> BinaryIO | None:
        if self.mock_mode:
            path = self._local_path(key)
            return path.open("rb") if path.exists() else None

        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"]
        except (ClientError, BotoCoreError):
            return None

    def delete_object(self, key: str) -> bool:
        if self.mock_mode:
            path = self._local_path(key)
            if path.exists():
                path.unlink()
            return True

        try:
            self.s3_client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except (ClientError, BotoCoreError):
            return False

    def exists(self, key: str) -> bool:
        if self.mock_mode:
            return self._local_path(key).exists()

        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=key)
            return True
        except (ClientError, BotoCoreError):
            return False

    def list_objects(self, prefix: str = "", limit: int = 1000) -> List[StorageMetadata]:
        if self.mock_mode:
            return self._list_local(prefix, limit)

        try:
            response = self.s3_client.list_objects_v2(Bucket=self.bucket, Prefix=prefix, MaxKeys=limit)
            contents = response.get("Contents", [])
            metadata_list: List[StorageMetadata] = []
            for item in contents:
                metadata_list.append(
                    StorageMetadata(
                        key=item["Key"],
                        size=item.get("Size", 0),
                        modified=item.get("LastModified", datetime.utcnow()),
                    )
                )
            return metadata_list
        except (ClientError, BotoCoreError):
            return []

    def get_metadata(self, key: str) -> Optional[StorageMetadata]:
        if self.mock_mode:
            path = self._local_path(key)
            if not path.exists():
                return None
            stat = path.stat()
            return StorageMetadata(
                key=key,
                size=stat.st_size,
                modified=datetime.fromtimestamp(stat.st_mtime),
            )

        try:
            response = self.s3_client.head_object(Bucket=self.bucket, Key=key)
            return StorageMetadata(
                key=key,
                size=response.get("ContentLength", 0),
                modified=response.get("LastModified", datetime.utcnow()),
                content_type=response.get("ContentType", ""),
                etag=response.get("ETag", ""),
            )
        except (ClientError, BotoCoreError):
            return None

    def create_presigned_url(self, key: str, expiry_seconds: int = 3600, method: str = "GET") -> Optional[str]:
        if self.mock_mode:
            path = self._local_path(key)
            return f"file://{path}" if path.exists() else None

        try:
            return self.s3_client.generate_presigned_url(
                ClientMethod="get_object" if method.upper() == "GET" else "put_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expiry_seconds,
            )
        except (ClientError, BotoCoreError):
            return None

    def copy_object(self, source_key: str, dest_key: str) -> bool:
        if self.mock_mode:
            source_path = self._local_path(source_key)
            if not source_path.exists():
                return False
            dest_path = self._local_path(dest_key)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(source_path.read_bytes())
            return True

        try:
            copy_source = {"Bucket": self.bucket, "Key": source_key}
            self.s3_client.copy_object(CopySource=copy_source, Bucket=self.bucket, Key=dest_key)
            return True
        except (ClientError, BotoCoreError):
            return False

    def health_check(self) -> bool:
        if self.mock_mode:
            return True

        try:
            self.s3_client.head_bucket(Bucket=self.bucket)
            return True
        except (ClientError, BotoCoreError):
            return False

    def _ensure_bucket_exists(self) -> None:
        try:
            self.s3_client.head_bucket(Bucket=self.bucket)
        except (ClientError, BotoCoreError):
            try:
                self.s3_resource.create_bucket(Bucket=self.bucket)
            except (ClientError, BotoCoreError) as exc:
                print(f"Warning: Unable to ensure bucket {self.bucket}: {exc}")
                self.mock_mode = True

    def _store_locally(self, key: str, data: bytes) -> bool:
        path = self._local_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return True

    def _local_path(self, key: str) -> Path:
        return (self.mock_root / key).resolve()

    @staticmethod
    def _clean_metadata(metadata: Optional[Dict[str, Optional[str]]]) -> Dict[str, str]:
        if not metadata:
            return {}
        return {k: str(v) for k, v in metadata.items() if v is not None}

    def _list_local(self, prefix: str, limit: int) -> List[StorageMetadata]:
        base = self.mock_root
        results: list[StorageMetadata] = []
        if not base.exists():
            return results

        prefix_path = base / prefix if prefix else base
        if prefix and prefix_path.is_file():
            stat = prefix_path.stat()
            return [StorageMetadata(key=prefix, size=stat.st_size, modified=datetime.fromtimestamp(stat.st_mtime))]

        searched = 0
        for filesystem_path in sorted(base.rglob("*")):
            if filesystem_path.is_file():
                relative_key = str(filesystem_path.relative_to(base))
                if prefix and not relative_key.startswith(prefix):
                    continue
                stat = filesystem_path.stat()
                results.append(
                    StorageMetadata(
                        key=relative_key,
                        size=stat.st_size,
                        modified=datetime.fromtimestamp(stat.st_mtime),
                    )
                )
                searched += 1
                if searched >= limit:
                    break
        return results
