"""
画像処理 API スキーマ
"""

from pydantic import BaseModel, Field


class GenerateProxyRequest(BaseModel):
    """POST /images/generate-proxy のリクエストボディ"""
    gcs_key: str = Field(
        ...,
        alias="gcsKey",
        description="GCS上のオリジナル画像キー（例: uploads/xxx_photo.jpg）",
    )
    max_dimension: int = Field(
        1000,
        alias="maxDimension",
        description="プレビュー画像の長辺最大px",
    )

    model_config = {"populate_by_name": True}


class GenerateProxyResponse(BaseModel):
    """POST /images/generate-proxy のレスポンスボディ"""
    proxy_url: str = Field(..., alias="proxyUrl")
    original_key: str = Field(..., alias="originalKey")

    model_config = {"populate_by_name": True}
