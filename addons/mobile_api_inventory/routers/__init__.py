from fastapi import APIRouter

from .barcode import router as barcode_router
from .inventory import router as inventory_router

router = APIRouter(prefix="/v1")
router.include_router(barcode_router)
router.include_router(inventory_router)
