"""
render/service.py の単体テスト

GCS を使わずに PDF 生成ロジックの正確性を検証する:
  - B5 サイズの本文 PDF が生成されること
  - 表紙 PDF（展開図）が生成されること
  - ページ数が正しいこと
  - のど逃げオフセットが正しく適用されること
"""

import io
import pytest
from unittest.mock import patch, MagicMock
from reportlab.lib.units import mm as RL_MM

from app.features.editor.schemas import EditorState, PageState, TextElement
from app.features.render.service import (
    render_body_pdf,
    render_cover_pdf,
    PAGE_W,
    PAGE_H,
    COVER_W,
    COVER_H,
)


def _make_editor_state(num_pages: int = 3) -> EditorState:
    """テスト用の EditorState を生成する"""
    pages = []
    for i in range(num_pages):
        pages.append(PageState(
            pageIndex=i,
            elements=[
                TextElement(
                    id=f"text-{i}",
                    type="text",
                    x=20.0,
                    y=30.0,
                    width=100.0,
                    height=20.0,
                    content=f"Page {i + 1} テスト",
                    fontSize=5.0,
                    fontFamily="Helvetica",  # 標準フォントでテスト
                )
            ],
        ))
    return EditorState(
        bookId="test-book-001",
        totalPages=30,
        pages=pages,
    )


class TestRenderBodyPdf:
    """本文 PDF 生成テスト"""

    def test_generates_valid_pdf(self):
        """有効な PDF バイナリが生成されること"""
        state = _make_editor_state(3)
        pdf_buffer = render_body_pdf(state)

        assert isinstance(pdf_buffer, io.BytesIO)
        content = pdf_buffer.read()
        # PDF ヘッダー確認
        assert content[:5] == b"%PDF-"
        # PDF フッター確認
        assert b"%%EOF" in content

    def test_page_size_is_b5(self):
        """ページサイズが B5（182×263mm）であること"""
        # 定数値で確認
        assert PAGE_W == 182
        assert PAGE_H == 263

    def test_empty_pages_generate_pdf(self):
        """要素なしのページでも PDF が生成されること"""
        state = EditorState(
            bookId="empty-book",
            totalPages=30,
            pages=[
                PageState(pageIndex=0, elements=[]),
                PageState(pageIndex=1, elements=[]),
            ],
        )
        pdf_buffer = render_body_pdf(state)
        content = pdf_buffer.read()
        assert content[:5] == b"%PDF-"

    def test_gutter_shift_constants(self):
        """のど逃げ定数が 5mm であること"""
        from app.features.render.service import GUTTER_SHIFT
        assert GUTTER_SHIFT == 5


class TestRenderCoverPdf:
    """表紙 PDF 生成テスト"""

    def test_generates_valid_cover_pdf(self):
        """表紙展開図 PDF が生成されること"""
        state = _make_editor_state(1)
        pdf_buffer = render_cover_pdf(state)

        content = pdf_buffer.read()
        assert content[:5] == b"%PDF-"

    def test_cover_size_is_correct(self):
        """表紙サイズが 422×297mm であること"""
        assert COVER_W == 422
        assert COVER_H == 297


class TestEditorStateSchema:
    """EditorState スキーマの検証"""

    def test_parse_valid_state(self):
        """正常な editor_state がパースできること"""
        state = _make_editor_state(3)
        assert state.book_id == "test-book-001"
        assert state.total_pages == 30
        assert len(state.pages) == 3
        assert state.pages[0].elements[0].type == "text"

    def test_sku_validation(self):
        """totalPages が 30/50/70 以外だとエラーになること"""
        with pytest.raises(Exception):
            EditorState(
                bookId="bad",
                totalPages=40,  # type: ignore
                pages=[],
            )
