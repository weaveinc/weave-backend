"""
フォント管理ユーティリティ

PDF 生成時のフォント完全埋め込みを担保する。
ReportLab の TTFont を使い、日本語フォント（Noto Sans JP 等）を
PDF に埋め込む。テキストのアウトライン化はフォント埋め込みで
解決できない場合のフォールバック。
"""

import os
import logging
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

logger = logging.getLogger(__name__)

# フォントディレクトリ（デプロイ環境に合わせて設定）
FONT_DIR = os.environ.get("WEAVE_FONT_DIR", os.path.join(os.path.dirname(__file__), "fonts"))

# 登録済みフォント名のキャッシュ
_registered_fonts: set[str] = set()


def register_font(font_family: str) -> str:
    """
    フォントファミリー名を指定し、ReportLab に TTFont を登録する。
    既に登録済みの場合はスキップする。

    Args:
        font_family: フォントファミリー名（例: "Noto Sans JP"）

    Returns:
        ReportLab で使用するフォント名
    """
    # フォントファミリー名 → ファイル名のマッピング
    font_file_map = {
        "Noto Sans JP": "NotoSansJP-Regular.ttf",
        "Noto Serif JP": "NotoSerifJP-Regular.ttf",
    }

    rl_name = font_family.replace(" ", "-")

    if rl_name in _registered_fonts:
        return rl_name

    filename = font_file_map.get(font_family)
    if not filename:
        logger.warning(f"Font '{font_family}' not in map, using Helvetica fallback")
        return "Helvetica"

    font_path = os.path.join(FONT_DIR, filename)
    if not os.path.exists(font_path):
        logger.warning(f"Font file not found: {font_path}, using Helvetica fallback")
        return "Helvetica"

    try:
        pdfmetrics.registerFont(TTFont(rl_name, font_path))
        _registered_fonts.add(rl_name)
        logger.info(f"Font registered: {rl_name} from {font_path}")
        return rl_name
    except Exception as e:
        logger.error(f"Failed to register font '{font_family}': {e}")
        return "Helvetica"
