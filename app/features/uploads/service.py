import uuid
import logging
from google.cloud import storage
from google.cloud.exceptions import GoogleCloudError
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    gcs_bucket_name: str
    google_application_credentials: str = ""

    model_config = ConfigDict(env_file=".env")


settings = Settings()


class GCSService:
    """
    GCS (Google Cloud Storage) を使ったアップロードサービス。

    S3マルチパートアップロードとの互換性を維持するため、
    GCS Compose 方式を採用:
      1. 各チャンクを個別の一時オブジェクトとして並列アップロード
      2. compose() で全パーツを結合して最終オブジェクトを生成
      3. 一時オブジェクトを削除
    """

    def __init__(self):
        if settings.google_application_credentials:
            self.client = storage.Client.from_service_account_json(
                settings.google_application_credentials
            )
        else:
            self.client = storage.Client()
        self.bucket = self.client.bucket(settings.gcs_bucket_name)

    def create_multipart_session(self, key: str, content_type: str) -> str:
        """
        マルチパートアップロードセッションを初期化する。
        S3の create_multipart_upload に相当。
        GCSでは実際のオブジェクトは作らず、セッションIDだけ発行する。
        """
        session_id = str(uuid.uuid4())
        return session_id

    def generate_single_signed_url(self, key: str, content_type: str) -> str:
        """
        単発アップロード用（5MB未満）の署名付きURLを生成する。
        """
        from datetime import timedelta

        blob = self.bucket.blob(key)
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=15),
            method="PUT",
            content_type=content_type,
        )
        return url

    def generate_part_signed_url(self, key: str, upload_id: str, part_number: int) -> str:
        """
        指定パートのアップロード用署名付きURLを生成する。
        S3の generate_presigned_url に相当。
        GCS Compose方式では、パーツを一時オブジェクトとして保存する。
        一時オブジェクトのキー: {key}_part{part_number}
        """
        from datetime import timedelta

        part_key = f"{key}_part{part_number}"
        blob = self.bucket.blob(part_key)
        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=15),
            method="PUT",
            content_type="application/octet-stream",
        )
        return url

    def complete_multipart_upload(self, key: str, upload_id: str, parts: list[dict]) -> dict:
        """
        全パーツを結合してアップロードを完了する。
        S3の complete_multipart_upload に相当。

        GCS compose() は1回あたり最大32オブジェクトまで。
        32を超える場合はiterativeに結合する。

        parts: [{'PartNumber': 1, 'ETag': '...'}, ...] のリスト
        """
        sorted_parts = sorted(parts, key=lambda p: p["PartNumber"])
        source_blobs = []

        for part in sorted_parts:
            part_key = f"{key}_part{part['PartNumber']}"
            source_blobs.append(self.bucket.blob(part_key))

        # GCS compose: 最大32オブジェクトずつ結合
        destination_blob = self.bucket.blob(key)

        if len(source_blobs) <= 32:
            destination_blob.compose(source_blobs)
        else:
            # iterative compose: 32個ずつ中間オブジェクトに結合し、最後にまとめる
            intermediate_blobs = []
            for i in range(0, len(source_blobs), 32):
                chunk = source_blobs[i : i + 32]
                if len(intermediate_blobs) == 0 and i + 32 >= len(source_blobs):
                    # 最後のチャンクかつ中間なし → 直接最終オブジェクトに
                    destination_blob.compose(chunk)
                else:
                    intermediate_key = f"{key}_intermediate_{i // 32}"
                    intermediate_blob = self.bucket.blob(intermediate_key)
                    intermediate_blob.compose(chunk)
                    intermediate_blobs.append(intermediate_blob)

            if intermediate_blobs:
                destination_blob.compose(intermediate_blobs)
                # 中間オブジェクトを削除
                for blob in intermediate_blobs:
                    try:
                        blob.delete()
                    except GoogleCloudError:
                        logger.warning(f"Failed to delete intermediate blob: {blob.name}")

        # 一時パーツオブジェクトを削除
        for blob in source_blobs:
            try:
                blob.delete()
            except GoogleCloudError:
                logger.warning(f"Failed to delete part blob: {blob.name}")

        location = f"https://storage.googleapis.com/{settings.gcs_bucket_name}/{key}"
        return {"Location": location}

    def abort_multipart_upload(self, key: str, upload_id: str) -> dict:
        """
        アップロードを中断し、一時チャンクオブジェクトを削除する。
        S3の abort_multipart_upload に相当。
        """
        # アップロード済みの一時パーツを検索して削除
        prefix = f"{key}_part"
        blobs = list(self.client.list_blobs(self.bucket, prefix=prefix))
        for blob in blobs:
            try:
                blob.delete()
            except GoogleCloudError:
                logger.warning(f"Failed to delete blob during abort: {blob.name}")

        return {}


gcs_service = GCSService()
