import time
from pathlib import Path

from fastapi import FastAPI
import uvicorn

from app.config import DATA_DIR, PENDING_DIR, FAILED_DIR, SENT_DIR
from app.logger import get_logger

logger = get_logger("collector.health")

app = FastAPI(title="Collector Health")

START_TIME = time.time()
LAST_PACKET_TIME = time.time()


def update_last_packet_time() -> None:
    global LAST_PACKET_TIME
    LAST_PACKET_TIME = time.time()


def disk_is_writable() -> bool:
    try:
        test_file = DATA_DIR / "healthcheck.tmp"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        return True
    except Exception:
        return False


@app.get("/health")
def health():
    pending = len(list(PENDING_DIR.glob("*.parquet")))
    failed = len(list(FAILED_DIR.glob("*.parquet")))
    sent = len(list(SENT_DIR.glob("*.parquet")))
    disk_ok = disk_is_writable()
    uptime = int(time.time() - START_TIME)
    last_packet_age = int(time.time() - LAST_PACKET_TIME)

    logger.info(
        "Health endpoint cagrildi",
        extra={
            "event": "health_check",
            "pending_packets": pending,
            "failed_packets": failed,
            "sent_packets": sent,
            "disk_ok": disk_ok,
            "uptime_sec": uptime,
            "last_packet_age_sec": last_packet_age,
        },
    )

    return {
        "status": "ok",
        "uptime_sec": uptime,
        "pending_packets": pending,
        "failed_packets": failed,
        "sent_packets": sent,
        "last_packet_age_sec": last_packet_age,
        "disk_ok": disk_ok,
    }


def start_health_server() -> None:
    logger.info(
        "Health server baslatildi",
        extra={
            "event": "health_server_started",
            "host": "0.0.0.0",
            "port": 9000,
        },
    )
    uvicorn.run(app, host="0.0.0.0", port=9000, log_level="warning")