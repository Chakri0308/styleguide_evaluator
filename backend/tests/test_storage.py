import pytest
from moto import mock_aws

from stylelens.storage import LocalStore, S3Store


def test_local_store_roundtrip(tmp_path):
    store = LocalStore(tmp_path)
    store.put("guides/a/x.bin", b"hello")
    assert store.exists("guides/a/x.bin")
    assert store.get("guides/a/x.bin") == b"hello"
    store.delete_prefix("guides/a")
    assert not store.exists("guides/a/x.bin")


def test_local_store_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        LocalStore(tmp_path).put("../escape", b"x")


def test_s3_store_roundtrip(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "")
    from stylelens.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "s3_endpoint_url", None)
    with mock_aws():
        store = S3Store()
        store.put("guides/a/x.bin", b"hello")
        assert store.exists("guides/a/x.bin")
        assert store.get("guides/a/x.bin") == b"hello"
        store.delete_prefix("guides/a")
        assert not store.exists("guides/a/x.bin")
    get_settings.cache_clear()
