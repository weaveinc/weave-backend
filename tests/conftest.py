"""
テスト共通設定

GCS クライアントのモック化と、テスト用 FastAPI クライアントを提供する。
"""

import os
import pytest
from unittest.mock import patch, MagicMock

# Dummy environment variables for pydantic settings
os.environ["GCS_BUCKET_NAME"] = "dummy_bucket"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = ""

# Mock google.cloud.storage before importing app
with patch("google.cloud.storage.Client"):
    from app.main import app
    from app.features.uploads.service import gcs_service, GCSService

from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI テストクライアント"""
    return TestClient(app)


@pytest.fixture
def mock_gcs_service():
    """各テスト用に GCSService インスタンスをモック付きで作成"""
    with patch("google.cloud.storage.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_bucket = MagicMock()
        mock_client.bucket.return_value = mock_bucket

        service = GCSService()
        service.client = mock_client
        service.bucket = mock_bucket

        yield service
