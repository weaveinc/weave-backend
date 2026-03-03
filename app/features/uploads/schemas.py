"""
GCS (Google Cloud Storage) アップロード用スキーマ定義モジュール

このモジュールでは、フロントエンド（Uppy @uppy/aws-s3-multipart プラグイン）と
やり取りするために必要なリクエスト/レスポンスのデータ構造（Pydanticモデル）を定義している。
Uppy側の仕様に合わせて、フィールド名にはキャメルケース（camelCase）を採用する。

ストレージバックエンドはGCSだが、API互換性を維持するため
S3マルチパートアップロードと同じインターフェースを提供する。
"""

from pydantic import BaseModel, ConfigDict

# キャメルケースの入力を受け付けるためのベースクラス
class CustomBaseModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class UploadInitializeRequest(CustomBaseModel):
    """
    POST /uploads/initialize のリクエストボディ
    Uppyから送られてくるアップロード予定のファイル情報の型。
    """
    filename: str
    type: str


class UploadInitializeResponse(CustomBaseModel):
    """
    POST /uploads/initialize のレスポンスボディ
    セッションIDと保存先キーをUppyに返す。
    """
    uploadId: str
    key: str


class SignPartResponse(CustomBaseModel):
    """
    GET /uploads/sign-part のレスポンスボディ
    分割された各ファイルパーツをGCSへ直接アップロードするための15分限定の署名付きURLをUppyに返す。
    """
    url: str


class PartETag(CustomBaseModel):
    """
    アップロード完了時に送られてくる各パーツの ETag 情報の型。
    GCS Compose方式でパーツを結合する際に使用する。
    """
    PartNumber: int
    ETag: str


class UploadCompleteRequest(CustomBaseModel):
    """
    POST /uploads/complete のリクエストボディ
    Uppyが全パーツのアップロードを終えた後、結合を指示するために送ってくる情報の型。
    """
    uploadId: str
    key: str
    parts: list[PartETag]


class UploadCompleteResponse(CustomBaseModel):
    """
    POST /uploads/complete のレスポンスボディ
    GCSでの結合が完了し、最終的に保存されたファイルのURLをUppyに返す。
    """
    location: str


class UploadAbortRequest(CustomBaseModel):
    """
    DELETE /uploads/abort のリクエストボディ
    ユーザーがアップロードをキャンセルした場合などに、GCS上の不要なチャンクデータを削除するために送られてくる情報の型。
    """
    uploadId: str
    key: str
