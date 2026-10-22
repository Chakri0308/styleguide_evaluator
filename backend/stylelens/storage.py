"""Object storage abstraction: S3-compatible (MinIO/AWS) or local filesystem."""

import asyncio
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from stylelens.config import get_settings


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete_prefix(self, prefix: str) -> None: ...


class LocalStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"invalid key: {key}")
        return path

    def put(self, key, data, content_type="application/octet-stream"):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key):
        return self._path(key).read_bytes()

    def exists(self, key):
        return self._path(key).exists()

    def delete_prefix(self, prefix):
        import shutil

        path = self._path(prefix)
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


class S3Store:
    def __init__(self):
        import boto3

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url,
            aws_access_key_id=s.s3_access_key,
            aws_secret_access_key=s.s3_secret_key,
            region_name=s.s3_region,
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        from botocore.exceptions import ClientError

        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key, data, content_type="application/octet-stream"):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key):
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete_prefix(self, prefix):
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if keys:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": keys})


@lru_cache
def get_store() -> ObjectStore:
    s = get_settings()
    if s.storage_backend == "s3":
        return S3Store()
    return LocalStore(s.storage_local_root)


async def aput(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    await asyncio.to_thread(get_store().put, key, data, content_type)


async def aget(key: str) -> bytes:
    return await asyncio.to_thread(get_store().get, key)
