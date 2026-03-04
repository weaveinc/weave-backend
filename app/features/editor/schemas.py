"""
EditorState Pydantic モデル定義

フロントエンドの editor_state（mm 座標）を受け取るための型。
TypeScript 側の型定義 (frontend/src/types/editor.ts) と 1 対 1 対応。

PDF/X-4 レンダリング時のフロー:
  editor_state (mm) -> pt 変換 (1pt = 1/72inch ≈ 0.353mm) -> ReportLab
"""

from __future__ import annotations
from typing import Literal, Optional, Union
from pydantic import BaseModel, Field


# ============================================================
# 要素
# ============================================================

class ImageElement(BaseModel):
    id: str
    type: Literal["image"]

    # 配置座標・サイズ（mm, のど逃げ適用済み）
    x: float = Field(..., description="配置 X mm")
    y: float = Field(..., description="配置 Y mm")
    width: float = Field(..., gt=0, description="配置幅 mm")
    height: float = Field(..., gt=0, description="配置高さ mm")

    # GCS キー（入稿 PDF 生成時にオリジナル画像を参照）
    gcs_key: str = Field(..., alias="gcsKey")

    # 解像度チェック用（optional）
    original_width_px: Optional[int] = Field(None, alias="originalWidthPx")
    original_height_px: Optional[int] = Field(None, alias="originalHeightPx")

    model_config = {"populate_by_name": True}


class TextElement(BaseModel):
    id: str
    type: Literal["text"]

    x: float = Field(..., description="配置 X mm")
    y: float = Field(..., description="配置 Y mm")
    width: float = Field(..., gt=0, description="テキストボックス幅 mm")
    height: float = Field(..., gt=0, description="テキストボックス高さ mm")

    content: str
    font_size: float = Field(..., alias="fontSize", description="フォントサイズ mm")
    font_family: str = Field("Noto Sans JP", alias="fontFamily")
    color: Optional[str] = Field("#000000", description="テキストカラー HEX")

    model_config = {"populate_by_name": True}


EditorElementType = Union[ImageElement, TextElement]


# ============================================================
# ページ
# ============================================================

class PageState(BaseModel):
    """片面 1 ページ単位"""
    page_index: int = Field(..., alias="pageIndex", ge=0)
    elements: list[EditorElementType] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ============================================================
# ブック全体
# ============================================================

class EditorState(BaseModel):
    """エディター状態本体（mm 座標）"""
    book_id: str = Field(..., alias="bookId")
    total_pages: Literal[30, 50, 70] = Field(..., alias="totalPages")
    pages: list[PageState]

    model_config = {"populate_by_name": True}
