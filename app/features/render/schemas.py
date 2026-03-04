"""
PDF レンダリング API スキーマ
"""

from pydantic import BaseModel, Field
from app.features.editor.schemas import EditorState


class RenderRequest(BaseModel):
    """POST /render/pdf のリクエストボディ"""
    editor_state: EditorState = Field(..., alias="editorState")

    model_config = {"populate_by_name": True}


class RenderResponse(BaseModel):
    """POST /render/pdf のレスポンスボディ"""
    body_pdf_url: str = Field(..., alias="bodyPdfUrl", description="本文PDF GCS URL")
    cover_pdf_url: str = Field(..., alias="coverPdfUrl", description="表紙PDF GCS URL")

    model_config = {"populate_by_name": True}
