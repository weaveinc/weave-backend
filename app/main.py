from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.features.uploads.router import router as uploads_router
from app.features.images.router import router as images_router
from app.features.render.router import router as render_router

app = FastAPI(title="Weave GCS Upload API")

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],  # 本番環境ではフロントエンドのドメインに制限してください
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーターの登録
app.include_router(uploads_router, prefix="/v1/uploads", tags=["uploads"])
app.include_router(images_router, prefix="/v1/images", tags=["images"])
app.include_router(render_router, prefix="/v1/render", tags=["render"])

