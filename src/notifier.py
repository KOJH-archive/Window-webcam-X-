"""Local Windows notifications, with a harmless fallback when unavailable."""
from __future__ import annotations

import logging


def notify(title: str, message: str):
    try:
        from winotify import Notification
        Notification(app_id="Desk Guardian", title=title, msg=message, duration="short").show()
    except Exception as exc:
        logging.getLogger("desk_guardian").warning("notification_unavailable %s", type(exc).__name__)
