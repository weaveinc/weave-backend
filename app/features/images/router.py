"""
画像処理 API ルーター
"""

from fastapi import APIRouter, HTTPException
import logging

from app.features.images.schemas import GenerateProxyRequest, GenerateProxyResponse
from app.features.images.service import generate_proxy_image

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/generate-proxy", response_model=GenerateProxyResponse)
async def create_proxy_image(request: GenerateProxyRequest):
    """
    GCS上のオリジナル画像から軽量プレビュー画像を生成する。

    アップロード完了後にフロントエンドから呼ばれ、
    編集画面用の軽量WebP画像を生成・保存してURLを返す。
    """
    try:
        proxy_url = generate_proxy_image(
            source_key=request.gcs_key,
            max_dimension=request.max_dimension,
        )
        return GenerateProxyResponse(
            proxyUrl=proxy_url,
            originalKey=request.gcs_key,
        )
    except Exception as e:
        logger.error(f"Error generating proxy image: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate proxy image")
