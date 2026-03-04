"""
PDF レンダリング API ルーター
"""

from fastapi import APIRouter, HTTPException
import logging

from app.features.render.schemas import RenderRequest, RenderResponse
from app.features.render.service import render_pdf

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/pdf", response_model=RenderResponse)
async def create_pdf(request: RenderRequest):
    """
    editor_state を受け取り、印刷入稿用の PDF/X-4 を生成する。

    - 本文 PDF（片面 1 ページ単位・B5）
    - 表紙 PDF（展開図 422×297mm）

    生成した PDF は GCS に保存し、URL を返す。
    """
    try:
        body_url, cover_url = render_pdf(request.editor_state)
        return RenderResponse(
            bodyPdfUrl=body_url,
            coverPdfUrl=cover_url,
        )
    except Exception as e:
        logger.error(f"Error rendering PDF: {e}")
        raise HTTPException(status_code=500, detail="Failed to render PDF")
