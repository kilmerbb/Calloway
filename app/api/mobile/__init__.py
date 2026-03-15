from fastapi import APIRouter

from .auth import router as auth_router
from .briefing import briefing_router, schedule_router
from .contacts import router as contacts_router
from .conversations import router as conversations_router
from .devices import router as devices_router
from .ws import ws_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(briefing_router)
router.include_router(schedule_router)
router.include_router(contacts_router)
router.include_router(conversations_router)
router.include_router(devices_router)
router.include_router(ws_router)
