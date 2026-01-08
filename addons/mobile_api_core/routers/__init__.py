from fastapi import APIRouter

from .auth import router as auth_router
from .device import router as device_router
from .health import router as health_router
from .menu import router as menu_router
from .me import router as me_router
from .settings import router as settings_router

router = APIRouter(prefix="/v1")
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(device_router)
router.include_router(me_router)
router.include_router(menu_router)
router.include_router(settings_router)
