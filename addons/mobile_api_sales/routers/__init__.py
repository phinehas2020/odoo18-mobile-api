from fastapi import APIRouter

from .sales import router as sales_router

router = APIRouter(prefix="/v1")
router.include_router(sales_router)
