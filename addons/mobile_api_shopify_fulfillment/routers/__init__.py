from fastapi import APIRouter

from .shopify_fulfillment import router as shopify_fulfillment_router

router = APIRouter(prefix="/v1")
router.include_router(shopify_fulfillment_router)

