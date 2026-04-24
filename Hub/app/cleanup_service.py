import asyncio

from app.config import PACKET_EVENTS_RETENTION_DAYS, CLEANUP_INTERVAL_HOURS
from app.logger import get_logger
from app.storage import cleanup_old_packet_events

logger = get_logger("hub.cleanup")


async def cleanup_loop():
    while True:
        try:
            cleanup_old_packet_events(PACKET_EVENTS_RETENTION_DAYS)

            logger.info(
                "Eski packet eventleri silindi",
                extra={
                    "event": "packet_events_cleanup",
                    "retention_days": PACKET_EVENTS_RETENTION_DAYS,
                },
            )

        except Exception as exc:
            logger.error(
                "Packet events cleanup hatasi",
                extra={
                    "event": "packet_events_cleanup_failed",
                    "error": str(exc),
                },
            )

        # 24 saat bekle
        await asyncio.sleep(CLEANUP_INTERVAL_HOURS * 3600)