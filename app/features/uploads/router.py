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
        unique_key = f"uploads/{uuid.uuid4()}_{request.filename}"

        upload_id = gcs_service.create_multipart_session(
            key=unique_key,
            content_type=request.type
        )
        return UploadInitializeResponse(uploadId=upload_id, key=unique_key)
    except GoogleCloudError as e:
        logger.error(f"GCS error during initialize: {e}")
        raise HTTPException(status_code=500, detail="Failed to initialize upload")
    except Exception as e:
        logger.error(f"Error during initialize: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/sign-part", response_model=SignPartResponse)
async def sign_part(uploadId: str, key: str, partNumber: int):
    """
    指定された PartNumber に対する Signed URL を返す。
    """
    try:
        url = gcs_service.generate_part_signed_url(
            key=key,
            upload_id=uploadId,
            part_number=partNumber
        )
        return SignPartResponse(url=url)
    except GoogleCloudError as e:
        logger.error(f"GCS error during sign-part: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate signed URL")
    except Exception as e:
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
        parts_list = [{"ETag": part.ETag, "PartNumber": part.PartNumber} for part in request.parts]

        response = gcs_service.complete_multipart_upload(
            key=request.key,
            upload_id=request.uploadId,
            parts=parts_list
        )

        file_location = response.get("Location", f"https://storage.googleapis.com/{gcs_service.bucket.name}/{request.key}")
        logger.info(f"Upload completed: {file_location}")

        return UploadCompleteResponse(location=file_location)
    except GoogleCloudError as e:
        logger.error(f"GCS error during complete: {e}")
        raise HTTPException(status_code=500, detail="Failed to complete multipart upload")
    except Exception as e:
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
