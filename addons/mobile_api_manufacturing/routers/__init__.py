from fastapi import APIRouter

from .manufacturing import router as manufacturing_router

router = APIRouter(prefix="/v1")
router.include_router(manufacturing_router)

