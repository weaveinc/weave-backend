from fastapi import APIRouter, HTTPException, Request
from google.cloud.exceptions import GoogleCloudError
import logging
import uuid

from app.features.uploads.schemas import (
    UploadInitializeRequest,
    UploadInitializeResponse,
    SignPartResponse,
    UploadCompleteRequest,
    UploadCompleteResponse,
)
from app.features.uploads.service import gcs_service

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/initialize", response_model=UploadInitializeResponse)
async def initialize_upload(request: UploadInitializeRequest):
    """
    アップロードを初期化し、UploadIdとGCSのKeyを返す。
    """
    try:
        # 1. 保存先のパス（Key）を生成
        # uuid4でランダムな文字列を作成し、ファイル名と結合して一意なIDにする
        unique_key = f"uploads/{uuid.uuid4()}_{request.filename}"

        # 2. GCSでマルチパートアップロードのセッションを開始
        # 保存パスとファイル形式（MIMEタイプ）を指定し、管理用のUploadIdを取得する
        upload_id = gcs_service.create_multipart_session(
            key=unique_key,
            content_type=request.type
        )

        # 3. クライアントに管理情報を返却
        # 以降のアップロード操作に必要なIDとパスをレスポンスとして返す
        return UploadInitializeResponse(uploadId=upload_id, key=unique_key)

    except GoogleCloudError as e:
        # GCSサービス固有のエラーが発生した場合のログ記録と例外送出
        logger.error(f"GCS error during initialize: {e}")
        raise HTTPException(status_code=500, detail="Failed to initialize upload")

    except Exception as e:
        # その他の予期せぬシステムエラーが発生した場合の処理
        logger.error(f"Error during initialize: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/sign-part", response_model=SignPartResponse)
async def sign_part(uploadId: str, key: str, partNumber: int):
    """
    指定された PartNumber に対する Signed URL を返す。
    """
    try:
        # 1. GCSのAPIを利用して、特定のパート専用のアップロード用URLを生成する
        # upload_id: 初期化時に取得した管理番号
        # part_number: 分割されたデータの何番目か（1, 2, 3...）
        url = gcs_service.generate_part_signed_url(
            key=key,
            upload_id=uploadId,
            part_number=partNumber
        )

        # 2. 生成した一時的な許可証（URL）をレスポンスとして返す
        return SignPartResponse(url=url)

    except GoogleCloudError as e:
        # GCS側のエラー（認証失敗や権限不足など）をログに記録
        logger.error(f"GCS error during sign-part: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate signed URL")

    except Exception as e:
        # システム全体の予期せぬエラーをログに記録
        logger.error(f"Error during sign-part: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/presign")
async def get_presigned_url(filename: str, type: str):
    """
    5MB未満の小さなファイル向けの、単発PUTアップロード用Signed URLを返す。
    """
    try:
        unique_key = f"uploads/{uuid.uuid4()}_{filename}"
        url = gcs_service.generate_single_signed_url(key=unique_key, content_type=type)
        return {"url": url, "key": unique_key}
    except GoogleCloudError as e:
        logger.error(f"GCS error during single presign: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate single signed URL")
    except Exception as e:
        logger.error(f"Error during single presign: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/complete", response_model=UploadCompleteResponse)
async def complete_upload(request: UploadCompleteRequest):
    """
    アップロードされた全パートの ETag リストを受け取り、アップロードを完了させる。
    GCS Compose方式で一時オブジェクトを結合し、最終URLを返す。
    """
    try:
        # 1. 各パーツの識別情報（ETagと番号）をリスト化する
        # クライアントが正しくアップロードした証拠をまとめます
        parts_list = [{"ETag": part.ETag, "PartNumber": part.PartNumber} for part in request.parts]

        # 2. GCSのAPIを呼び出し、分割状態のデータを1つのオブジェクトに結合する
        # これにより、一時的なパーツデータが正式な1つのファイルになります
        response = gcs_service.complete_multipart_upload(
            key=request.key,
            upload_id=request.uploadId,
            parts=parts_list
        )

        # 3. 結合完了後のファイルの公開URLを取得、または生成する
        file_location = response.get("Location", f"https://storage.googleapis.com/{gcs_service.bucket.name}/{request.key}")
        logger.info(f"Upload completed: {file_location}")

        # 4. 最終的な保存場所のURLをレスポンスとして返す
        return UploadCompleteResponse(location=file_location)
        
    except GoogleCloudError as e:
        # 結合処理中にGCS側で発生したエラー（パーツ不足など）を記録
        logger.error(f"GCS error during complete: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete multipart upload")
    
    except Exception as e:
        # その他の予期せぬシステムエラーを記録
        logger.error(f"Error during complete: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/abort")
async def abort_upload(request: Request):
    """
    アップロードの中断・キャンセル処理。GCS上の不完全なデータを削除する。
    """
    try:
        body = await request.json()
        upload_id = body.get("uploadId")
        key = body.get("key")

        if not upload_id or not key:
            raise HTTPException(status_code=400, detail="Missing uploadId or key")

        gcs_service.abort_multipart_upload(key=key, upload_id=upload_id)
        return {"status": "success", "message": "Upload aborted"}
    except GoogleCloudError as e:
        logger.error(f"GCS error during abort: {e}")
        raise HTTPException(status_code=500, detail="Failed to abort multipart upload")
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"Error during abort: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
