"""
アップロード API エンドポイントテスト

/v1/uploads/ 配下の全エンドポイント（正常系 + 異常系）を検証する。
"""

import re
import pytest
from unittest.mock import patch
from tests.conftest import gcs_service, app

from fastapi.testclient import TestClient

client = TestClient(app)


# ============================================================
# 正常系テスト
# ============================================================

@patch.object(gcs_service, 'create_multipart_session')
def test_initialize_upload(mock_create):
    mock_create.return_value = "dummy-upload-id"
    response = client.post("/v1/uploads/initialize", json={"filename": "test.jpg", "type": "image/jpeg"})
    assert response.status_code == 200
    data = response.json()
    assert data["uploadId"] == "dummy-upload-id"
    assert "key" in data
    assert "uploads/" in data["key"]
    assert "test.jpg" in data["key"]

@patch.object(gcs_service, 'generate_part_signed_url')
def test_sign_part(mock_generate):
    mock_generate.return_value = "https://dummy-signed-url.com"
    response = client.get("/v1/uploads/sign-part?uploadId=dummyId&key=dummyKey&partNumber=1")
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://dummy-signed-url.com"

@patch.object(gcs_service, 'complete_multipart_upload')
def test_complete_upload(mock_complete):
    mock_complete.return_value = {"Location": "https://dummy-location.com"}
    payload = {
        "uploadId": "dummyId",
        "key": "dummyKey",
        "parts": [
            {"PartNumber": 1, "ETag": "etag1"},
            {"PartNumber": 2, "ETag": "etag2"}
        ]
    }
    response = client.post("/v1/uploads/complete", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["location"] == "https://dummy-location.com"

@patch.object(gcs_service, 'abort_multipart_upload')
def test_abort_upload(mock_abort):
    mock_abort.return_value = {}
    payload = {
        "uploadId": "dummyId",
        "key": "dummyKey"
    }
    response = client.request("DELETE", "/v1/uploads/abort", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"

@patch.object(gcs_service, 'generate_single_signed_url')
def test_presign_single(mock_presign):
    mock_presign.return_value = "https://dummy-single-signed-url.com"
    response = client.get("/v1/uploads/presign?filename=small.jpg&type=image/jpeg")
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "https://dummy-single-signed-url.com"
    assert "key" in data
    assert "uploads/" in data["key"]


# ============================================================
# 異常系テスト: /v1/uploads/initialize
# ============================================================

def test_initialize_upload_missing_filename():
    """filename が欠落している場合 422 が返ること"""
    response = client.post("/v1/uploads/initialize", json={"type": "image/jpeg"})
    assert response.status_code == 422

def test_initialize_upload_missing_type():
    """type が欠落している場合 422 が返ること"""
    response = client.post("/v1/uploads/initialize", json={"filename": "test.jpg"})
    assert response.status_code == 422

def test_initialize_upload_empty_body():
    """空のボディで 422 が返ること"""
    response = client.post("/v1/uploads/initialize", json={})
    assert response.status_code == 422

@patch.object(gcs_service, 'create_multipart_session')
def test_initialize_upload_gcs_error(mock_create):
    """GCS エラー時に 500 が返ること"""
    from google.cloud.exceptions import GoogleCloudError
    mock_create.side_effect = GoogleCloudError("GCS connection failed")
    response = client.post("/v1/uploads/initialize", json={"filename": "test.jpg", "type": "image/jpeg"})
    assert response.status_code == 500
    assert "Failed to initialize upload" in response.json()["detail"]


# ============================================================
# 異常系テスト: /v1/uploads/sign-part
# ============================================================

def test_sign_part_missing_params():
    """必須クエリパラメータが欠落している場合 422 が返ること"""
    response = client.get("/v1/uploads/sign-part?uploadId=dummyId")
    assert response.status_code == 422

@patch.object(gcs_service, 'generate_part_signed_url')
def test_sign_part_gcs_error(mock_generate):
    """GCS エラー時に 500 が返ること"""
    from google.cloud.exceptions import GoogleCloudError
    mock_generate.side_effect = GoogleCloudError("Signed URL generation failed")
    response = client.get("/v1/uploads/sign-part?uploadId=dummyId&key=dummyKey&partNumber=1")
    assert response.status_code == 500


# ============================================================
# 異常系テスト: /v1/uploads/complete
# ============================================================

@patch.object(gcs_service, 'complete_multipart_upload')
def test_complete_upload_empty_parts(mock_complete):
    """parts が空リストでも API 自体は呼び出し可能であること"""
    mock_complete.return_value = {"Location": "https://dummy-location.com"}
    payload = {
        "uploadId": "dummyId",
        "key": "dummyKey",
        "parts": []
    }
    response = client.post("/v1/uploads/complete", json=payload)
    assert response.status_code == 200

@patch.object(gcs_service, 'complete_multipart_upload')
def test_complete_upload_gcs_error(mock_complete):
    """GCS Compose 失敗時に 500 が返ること"""
    from google.cloud.exceptions import GoogleCloudError
    mock_complete.side_effect = GoogleCloudError("Compose failed")
    payload = {
        "uploadId": "dummyId",
        "key": "dummyKey",
        "parts": [{"PartNumber": 1, "ETag": "etag1"}]
    }
    response = client.post("/v1/uploads/complete", json=payload)
    assert response.status_code == 500
    assert "Failed to complete" in response.json()["detail"]

@patch.object(gcs_service, 'complete_multipart_upload')
def test_complete_upload_many_parts(mock_complete):
    """33パーツ以上（GCS Compose 32制限の分岐）でも API が正常に動作すること"""
    mock_complete.return_value = {"Location": "https://dummy-location.com"}
    parts = [{"PartNumber": i, "ETag": f"etag{i}"} for i in range(1, 34)]
    payload = {
        "uploadId": "dummyId",
        "key": "dummyKey",
        "parts": parts
    }
    response = client.post("/v1/uploads/complete", json=payload)
    assert response.status_code == 200
    called_parts = mock_complete.call_args[1]["parts"] if mock_complete.call_args[1] else mock_complete.call_args[0][2]
    assert len(called_parts) == 33


# ============================================================
# 異常系テスト: /v1/uploads/abort
# ============================================================

def test_abort_upload_missing_upload_id():
    """uploadId が欠落している場合 400 が返ること"""
    payload = {"key": "dummyKey"}
    response = client.request("DELETE", "/v1/uploads/abort", json=payload)
    assert response.status_code == 400

def test_abort_upload_missing_key():
    """key が欠落している場合 400 が返ること"""
    payload = {"uploadId": "dummyId"}
    response = client.request("DELETE", "/v1/uploads/abort", json=payload)
    assert response.status_code == 400


# ============================================================
# キー形式テスト
# ============================================================

@patch.object(gcs_service, 'create_multipart_session')
def test_key_format_contains_uuid(mock_create):
    """生成される key に uploads/ プレフィックスと UUID が含まれること"""
    mock_create.return_value = "dummy-upload-id"
    response = client.post("/v1/uploads/initialize", json={"filename": "wedding_photo.jpg", "type": "image/jpeg"})
    assert response.status_code == 200
    key = response.json()["key"]
    assert key.startswith("uploads/")
    assert "wedding_photo.jpg" in key
    uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    assert re.search(uuid_pattern, key), f"Key should contain UUID pattern: {key}"
