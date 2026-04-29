from fastapi import APIRouter

from .smart_label import router as smart_label_router

router = APIRouter(prefix="/v1")
router.include_router(smart_label_router)
