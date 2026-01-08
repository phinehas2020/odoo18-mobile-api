from fastapi import APIRouter

from .sync import router as sync_router

router = APIRouter(prefix="/v1")
router.include_router(sync_router)
