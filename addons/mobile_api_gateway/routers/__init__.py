from fastapi import APIRouter

from .gateway import router as gateway_router

router = APIRouter(prefix="/v1")
router.include_router(gateway_router)
