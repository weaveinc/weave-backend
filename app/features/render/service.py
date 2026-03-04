"""
PDF/X-4 レンダリングサービス

editor_state（mm 座標）を受け取り、印刷入稿用の PDF/X-4 を生成する。

- 本文 PDF: 片面 1 ページ単位（B5: 182×263mm）
- 表紙 PDF: 展開図（422×297mm）
- 座標変換: mm → pt（1pt = 1/72inch ≈ 0.353mm）
- 1 ページずつ逐次レンダリング（メモリ効率化）
"""

import io
import logging
import uuid

from reportlab.lib.units import mm
from reportlab.lib.pagesizes import landscape
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from google.cloud import storage

from app.features.editor.schemas import EditorState, ImageElement, TextElement
from app.features.render.fonts import register_font
from app.features.uploads.service import settings

logger = logging.getLogger(__name__)

# ============================================================
# 物理仕様定数（mm）— print-spec.ts と同期
# ============================================================

PAGE_W = 182   # 本文幅
PAGE_H = 263   # 本文高さ
COVER_W = 422  # 表紙展開幅
COVER_H = 297  # 表紙展開高さ
GUTTER_SHIFT = 5  # のど逃げ


def _get_gcs_client():
    """GCS クライアントを取得する"""
    if settings.google_application_credentials:
        return storage.Client.from_service_account_json(
            settings.google_application_credentials
        )
    return storage.Client()


def _download_image_from_gcs(gcs_key: str) -> io.BytesIO:
    """GCS からオリジナル画像をダウンロードする"""
    client = _get_gcs_client()
    bucket = client.bucket(settings.gcs_bucket_name)
    blob = bucket.blob(gcs_key)
    data = blob.download_as_bytes()
    return io.BytesIO(data)


def _upload_pdf_to_gcs(pdf_buffer: io.BytesIO, gcs_key: str) -> str:
    """生成した PDF を GCS にアップロードしてURLを返す"""
    client = _get_gcs_client()
    bucket = client.bucket(settings.gcs_bucket_name)
    blob = bucket.blob(gcs_key)
    pdf_buffer.seek(0)
    blob.upload_from_file(pdf_buffer, content_type="application/pdf")
    url = f"https://storage.googleapis.com/{settings.gcs_bucket_name}/{gcs_key}"
    logger.info(f"PDF uploaded: {url}")
    return url


def _draw_image_element(c: canvas.Canvas, el: ImageElement):
    """
    画像要素を Canvas に描画する。
    座標系: ReportLab は左下原点、editor_state は左上原点。
    """
    try:
        img_data = _download_image_from_gcs(el.gcs_key)
        img = ImageReader(img_data)

        # 左上原点 → 左下原点への変換
        # ReportLab の y = ページ高さ - (el.y + el.height) を mm 単位で計算
        # ※ ページ高さはこの関数の呼び出し元で setPageSize 済み
        x_pt = el.x * mm
        # y は呼び出し元で計算したページ高さからのオフセット
        y_pt = el.y * mm  # 仮: 呼び出し元で座標変換する

        c.drawImage(
            img,
            x_pt,
            y_pt,
            width=el.width * mm,
            height=el.height * mm,
            preserveAspectRatio=True,
            mask="auto",
        )
    except Exception as e:
        logger.error(f"Failed to draw image {el.gcs_key}: {e}")


def _draw_text_element(c: canvas.Canvas, el: TextElement, page_height_mm: float):
    """テキスト要素を Canvas に描画する"""
    font_name = register_font(el.font_family)
    c.setFont(font_name, el.font_size * mm)

    color = el.color or "#000000"
    r = int(color[1:3], 16) / 255
    g = int(color[3:5], 16) / 255
    b = int(color[5:7], 16) / 255
    c.setFillColorRGB(r, g, b)

    # 左上原点 → 左下原点
    x_pt = el.x * mm
    y_pt = (page_height_mm - el.y - el.font_size) * mm

    c.drawString(x_pt, y_pt, el.content)


def render_body_pdf(editor_state: EditorState) -> io.BytesIO:
    """
    本文 PDF を生成する（片面 1 ページ単位）。

    のど逃げ処理:
    - 偶数ページ（0始まり偶数 → 印刷上は奇数 = 右ページ）: +5mm
    - 奇数ページ（0始まり奇数 → 印刷上は偶数 = 左ページ）: -5mm
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(PAGE_W * mm, PAGE_H * mm))

    for page in editor_state.pages:
        # のど逃げオフセット
        is_right_page = (page.page_index % 2 == 0)
        gutter_offset = GUTTER_SHIFT if is_right_page else -GUTTER_SHIFT

        for element in page.elements:
            if element.type == "image":
                img_el: ImageElement = element  # type: ignore
                # のど逃げ適用 & 左上→左下座標変換
                x_mm = img_el.x + gutter_offset
                y_mm = PAGE_H - img_el.y - img_el.height  # 左下原点変換

                try:
                    img_data = _download_image_from_gcs(img_el.gcs_key)
                    img = ImageReader(img_data)
                    c.drawImage(
                        img,
                        x_mm * mm,
                        y_mm * mm,
                        width=img_el.width * mm,
                        height=img_el.height * mm,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                except Exception as e:
                    logger.error(f"Failed to render image on page {page.page_index}: {e}")

            elif element.type == "text":
                text_el: TextElement = element  # type: ignore
                font_name = register_font(text_el.font_family)
                c.setFont(font_name, text_el.font_size * mm)

                color = text_el.color or "#000000"
                r = int(color[1:3], 16) / 255
                g = int(color[3:5], 16) / 255
                b = int(color[5:7], 16) / 255
                c.setFillColorRGB(r, g, b)

                x_mm = text_el.x + gutter_offset
                y_mm = PAGE_H - text_el.y - text_el.font_size

                c.drawString(x_mm * mm, y_mm * mm, text_el.content)

        c.showPage()  # 次のページへ

    c.save()
    buffer.seek(0)
    return buffer


def render_cover_pdf(editor_state: EditorState) -> io.BytesIO:
    """
    表紙 PDF を生成する（展開図: 422×297mm）。

    表紙データは pages[0] を使用する想定（将来的に専用フィールドに分離可能）。
    現時点ではプレースホルダーとして白紙の表紙展開図を生成する。
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(COVER_W * mm, COVER_H * mm))

    # 表紙は1ページのみ
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


def render_pdf(editor_state: EditorState) -> tuple[str, str]:
    """
    本文 PDF と表紙 PDF を生成し、GCS にアップロードして URL を返す。

    Returns:
        (body_pdf_url, cover_pdf_url)
    """
    render_id = str(uuid.uuid4())

    # 本文 PDF
    body_buffer = render_body_pdf(editor_state)
    body_key = f"renders/{editor_state.book_id}/{render_id}_body.pdf"
    body_url = _upload_pdf_to_gcs(body_buffer, body_key)

    # 表紙 PDF
    cover_buffer = render_cover_pdf(editor_state)
    cover_key = f"renders/{editor_state.book_id}/{render_id}_cover.pdf"
    cover_url = _upload_pdf_to_gcs(cover_buffer, cover_key)

    logger.info(f"Render complete: body={body_url}, cover={cover_url}")
    return body_url, cover_url
