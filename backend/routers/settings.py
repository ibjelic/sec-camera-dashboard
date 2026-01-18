import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.config import runtime_settings

logger = logging.getLogger(__name__)
router = APIRouter()


class SettingsUpdate(BaseModel):
    telegram_enabled: Optional[bool] = None
    telegram_screenshot: Optional[bool] = None
    telegram_gif: Optional[bool] = None
    detection_threshold: Optional[int] = None
    retention_hours: Optional[int] = None
    theme: Optional[str] = None
    notification_cooldown_seconds: Optional[int] = None


@router.get("")
async def get_settings():
    """Get all settings."""
    return runtime_settings.to_dict()


@router.put("")
async def update_settings(update: SettingsUpdate):
    """Update settings."""
    try:
        update_dict = update.model_dump(exclude_none=True)

        # Validate values
        if "detection_threshold" in update_dict:
            if not 10 <= update_dict["detection_threshold"] <= 100:
                raise HTTPException(
                    status_code=400,
                    detail="Detection threshold must be between 10 and 100"
                )

        if "retention_hours" in update_dict:
            if not 1 <= update_dict["retention_hours"] <= 720:  # Max 30 days
                raise HTTPException(
                    status_code=400,
                    detail="Retention hours must be between 1 and 720"
                )

        if "theme" in update_dict:
            if update_dict["theme"] not in ["light", "dark"]:
                raise HTTPException(
                    status_code=400,
                    detail="Theme must be 'light' or 'dark'"
                )

        if "notification_cooldown_seconds" in update_dict:
            if not 0 <= update_dict["notification_cooldown_seconds"] <= 3600:
                raise HTTPException(
                    status_code=400,
                    detail="Notification cooldown must be between 0 and 3600 seconds"
                )

        runtime_settings.update(**update_dict)
        logger.info(f"Settings updated: {update_dict}")

        return {"status": "updated", "settings": runtime_settings.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-telegram")
async def test_telegram(request: Request):
    """Send a test Telegram message."""
    notification_service = request.app.state.notification_service

    try:
        success = await notification_service.send_test_message()
        if success:
            return {"status": "sent", "message": "Test message sent successfully"}
        else:
            raise HTTPException(
                status_code=400,
                detail="Failed to send test message. Check bot token and chat ID."
            )
    except Exception as e:
        logger.error(f"Telegram test failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_settings():
    """Reload settings from file."""
    try:
        runtime_settings._load()
        return {"status": "reloaded", "settings": runtime_settings.to_dict()}
    except Exception as e:
        logger.error(f"Failed to reload settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
