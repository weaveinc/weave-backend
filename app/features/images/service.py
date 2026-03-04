"""
画像処理サービス

アップロード済みの高解像度画像から、
編集画面用の軽量プレビュー画像（WebP, 短辺1000px相当）を生成し
GCS に保存する。
"""

import io
import logging
from PIL import Image
from google.cloud import storage
from app.features.uploads.service import settings

logger = logging.getLogger(__name__)


def generate_proxy_image(
    source_key: str,
    max_dimension: int = 1000,
) -> str:
    """
    GCS上のオリジナル画像から軽量プレビュー画像を生成する。

    Args:
        source_key: GCSのオリジナル画像キー（例: "uploads/xxx_photo.jpg"）
        max_dimension: プレビュー画像の長辺最大ピクセル数

    Returns:
        生成されたプレビュー画像のGCS公開URL
    """
    client = storage.Client.from_service_account_json(
        settings.google_application_credentials
    ) if settings.google_application_credentials else storage.Client()

    bucket = client.bucket(settings.gcs_bucket_name)

    # 1. オリジナル画像をダウンロード
    source_blob = bucket.blob(source_key)
    image_data = source_blob.download_as_bytes()

    # 2. Pillow でリサイズ
    img = Image.open(io.BytesIO(image_data))
    original_width, original_height = img.size

    # 長辺が max_dimension を超える場合のみリサイズ
    if max(original_width, original_height) > max_dimension:
        ratio = max_dimension / max(original_width, original_height)
        new_width = int(original_width * ratio)
        new_height = int(original_height * ratio)
        img = img.resize((new_width, new_height), Image.LANCZOS)

    # 3. WebP に変換
    output_buffer = io.BytesIO()
    img.save(output_buffer, format="WEBP", quality=80)
    output_buffer.seek(0)

    # 4. GCS にアップロード（proxy/ プレフィックス）
    proxy_key = source_key.replace("uploads/", "proxy/", 1)
    # 拡張子を .webp に変更
    proxy_key = proxy_key.rsplit(".", 1)[0] + ".webp"

    proxy_blob = bucket.blob(proxy_key)
    proxy_blob.upload_from_file(output_buffer, content_type="image/webp")

    proxy_url = f"https://storage.googleapis.com/{settings.gcs_bucket_name}/{proxy_key}"
    logger.info(f"Proxy image created: {proxy_url} ({img.size[0]}x{img.size[1]}px)")

    return proxy_url
