"""
GCS Service 単体テスト

GCSService クラスに対するモック使用テスト。
GCS Compose 方式のマルチパートアップロードロジックを検証する。
"""

import pytest
import uuid
import os
from unittest.mock import patch, MagicMock, call

# Dummy environment variables for pydantic settings
os.environ["GCS_BUCKET_NAME"] = "dummy_bucket"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = ""

# Mock google.cloud.storage before importing the module
with patch("google.cloud.storage.Client"):
    from app.features.uploads.service import GCSService


@pytest.fixture
def gcs_service():
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


class TestCreateMultipartSession:
    """create_multipart_session のテスト"""

    def test_returns_uuid_format(self, gcs_service):
        """UUID 形式のセッション ID が返ること"""
        session_id = gcs_service.create_multipart_session(
            key="uploads/test.jpg",
            content_type="image/jpeg"
        )
        # UUID として解析可能であること
        parsed = uuid.UUID(session_id)
        assert str(parsed) == session_id

    def test_returns_unique_ids(self, gcs_service):
        """呼び出しごとに異なるセッション ID が返ること"""
        id1 = gcs_service.create_multipart_session("key1", "image/jpeg")
        id2 = gcs_service.create_multipart_session("key2", "image/jpeg")
        assert id1 != id2


class TestGenerateSingleSignedUrl:
    """generate_single_signed_url のテスト"""

    def test_calls_blob_with_correct_key(self, gcs_service):
        """正しいキーで blob が取得されること"""
        mock_blob = MagicMock()
        mock_blob.generate_signed_url.return_value = "https://signed-url.com"
        gcs_service.bucket.blob.return_value = mock_blob

        url = gcs_service.generate_single_signed_url(
            key="uploads/photo.jpg",
            content_type="image/jpeg"
        )

        gcs_service.bucket.blob.assert_called_once_with("uploads/photo.jpg")
        assert url == "https://signed-url.com"

    def test_signed_url_params(self, gcs_service):
        """署名 URL 生成の引数が正しいこと（PUT メソッド、v4、15分）"""
        mock_blob = MagicMock()
        mock_blob.generate_signed_url.return_value = "https://signed-url.com"
        gcs_service.bucket.blob.return_value = mock_blob

        gcs_service.generate_single_signed_url("key", "image/png")

        call_kwargs = mock_blob.generate_signed_url.call_args[1]
        assert call_kwargs["version"] == "v4"
        assert call_kwargs["method"] == "PUT"
        assert call_kwargs["content_type"] == "image/png"


class TestGeneratePartSignedUrl:
    """generate_part_signed_url のテスト"""

    def test_part_key_format(self, gcs_service):
        """パートキーが {key}_part{n} 形式であること"""
        mock_blob = MagicMock()
        mock_blob.generate_signed_url.return_value = "https://part-url.com"
        gcs_service.bucket.blob.return_value = mock_blob

        gcs_service.generate_part_signed_url(
            key="uploads/photo.jpg",
            upload_id="session-123",
            part_number=3
        )

        gcs_service.bucket.blob.assert_called_once_with("uploads/photo.jpg_part3")


class TestCompleteMultipartUpload:
    """complete_multipart_upload のテスト"""

    def test_compose_32_or_less(self, gcs_service):
        """32パーツ以下で compose() が1回呼ばれること"""
        mock_dest_blob = MagicMock()
        mock_part_blob = MagicMock()
        gcs_service.bucket.blob.side_effect = lambda key: (
            mock_dest_blob if not key.endswith(("_part1", "_part2", "_part3"))
            else mock_part_blob
        )

        parts = [{"PartNumber": i, "ETag": f"etag{i}"} for i in range(1, 4)]
        gcs_service.complete_multipart_upload("uploads/photo.jpg", "session-123", parts)

        # compose が呼ばれていること
        assert mock_dest_blob.compose.call_count == 1

    def test_compose_over_32_iterative(self, gcs_service):
        """33パーツ以上で iterative compose（中間結合）が行われること"""
        blobs = {}

        def blob_factory(key):
            if key not in blobs:
                blobs[key] = MagicMock(name=f"blob({key})")
            return blobs[key]

        gcs_service.bucket.blob.side_effect = blob_factory

        parts = [{"PartNumber": i, "ETag": f"etag{i}"} for i in range(1, 35)]
        gcs_service.complete_multipart_upload("uploads/photo.jpg", "session-123", parts)

        # 最終的な blob にも compose が呼ばれていること
        dest_blob = blobs["uploads/photo.jpg"]
        assert dest_blob.compose.call_count >= 1

    def test_cleanup_parts_after_complete(self, gcs_service):
        """完了後に一時パーツオブジェクトが削除されること"""
        mock_blobs = {}

        def blob_factory(key):
            if key not in mock_blobs:
                mock_blobs[key] = MagicMock(name=f"blob({key})")
            return mock_blobs[key]

        gcs_service.bucket.blob.side_effect = blob_factory

        parts = [{"PartNumber": 1, "ETag": "etag1"}, {"PartNumber": 2, "ETag": "etag2"}]
        gcs_service.complete_multipart_upload("uploads/photo.jpg", "session-123", parts)

        # パーツ blob の delete が呼ばれていること
        part1_blob = mock_blobs["uploads/photo.jpg_part1"]
        part2_blob = mock_blobs["uploads/photo.jpg_part2"]
        part1_blob.delete.assert_called_once()
        part2_blob.delete.assert_called_once()

    def test_parts_sorted_by_number(self, gcs_service):
        """パーツが PartNumber 順にソートされて compose されること"""
        composed_blobs = []
        mock_dest = MagicMock()
        mock_dest.compose.side_effect = lambda blobs: composed_blobs.extend(blobs)

        blob_map = {}
        def blob_factory(key):
            if key == "uploads/photo.jpg":
                return mock_dest
            if key not in blob_map:
                blob_map[key] = MagicMock(name=f"blob({key})")
            return blob_map[key]

        gcs_service.bucket.blob.side_effect = blob_factory

        # 逆順で渡す
        parts = [
            {"PartNumber": 3, "ETag": "etag3"},
            {"PartNumber": 1, "ETag": "etag1"},
            {"PartNumber": 2, "ETag": "etag2"},
        ]
        gcs_service.complete_multipart_upload("uploads/photo.jpg", "session-123", parts)

        # _part1, _part2, _part3 の順に compose されるはず
        blob_names = [b._mock_name for b in composed_blobs]
        assert blob_names == [
            "blob(uploads/photo.jpg_part1)",
            "blob(uploads/photo.jpg_part2)",
            "blob(uploads/photo.jpg_part3)",
        ]

    def test_returns_location_url(self, gcs_service):
        """完了時に正しい GCS URL が返ること"""
        mock_blob = MagicMock()
        gcs_service.bucket.blob.return_value = mock_blob

        parts = [{"PartNumber": 1, "ETag": "etag1"}]
        result = gcs_service.complete_multipart_upload("uploads/photo.jpg", "session-123", parts)

        assert "Location" in result
        assert "storage.googleapis.com" in result["Location"]
        assert "uploads/photo.jpg" in result["Location"]


class TestAbortMultipartUpload:
    """abort_multipart_upload のテスト"""

    def test_deletes_part_blobs(self, gcs_service):
        """abort 時に _part プレフィックスの blob が削除されること"""
        mock_blob1 = MagicMock()
        mock_blob2 = MagicMock()
        gcs_service.client.list_blobs.return_value = [mock_blob1, mock_blob2]

        result = gcs_service.abort_multipart_upload("uploads/photo.jpg", "session-123")

        gcs_service.client.list_blobs.assert_called_once_with(
            gcs_service.bucket,
            prefix="uploads/photo.jpg_part"
        )
        mock_blob1.delete.assert_called_once()
        mock_blob2.delete.assert_called_once()
        assert result == {}

    def test_handles_delete_failure_gracefully(self, gcs_service):
        """部分的な削除失敗時にもエラーにならないこと"""
        from google.cloud.exceptions import GoogleCloudError

        mock_blob1 = MagicMock()
        mock_blob1.delete.side_effect = GoogleCloudError("Delete failed")
        mock_blob2 = MagicMock()
        gcs_service.client.list_blobs.return_value = [mock_blob1, mock_blob2]

        # エラーが発生してもクラッシュしないこと
        result = gcs_service.abort_multipart_upload("uploads/photo.jpg", "session-123")
        assert result == {}
        # 2番目の blob も削除が試みられること
        mock_blob2.delete.assert_called_once()

    def test_no_blobs_to_delete(self, gcs_service):
        """削除対象の blob が存在しない場合も正常に完了すること"""
        gcs_service.client.list_blobs.return_value = []

        result = gcs_service.abort_multipart_upload("uploads/photo.jpg", "session-123")
        assert result == {}
