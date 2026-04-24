from pathlib import Path

import requests

from app.config import HUB_INGEST_URL, HTTP_TIMEOUT_SEC
from app.logger import get_logger

logger = get_logger("collector.sender")


def send_packet(file_path: str | Path, packet_id: str) -> bool:
    """
    Verilen packet dosyasını Hub'a gönderir.
    Başarılıysa True, değilse False döner.
    """
    path = Path(file_path)

    if not path.exists():
        logger.error(
            "Gonderilecek dosya bulunamadi",
            extra={
                "event": "packet_file_missing",
                "file_name": path.name,
                "hub_url": HUB_INGEST_URL,
            },
        )
        return False

    try:
        with path.open("rb") as file_obj:
            files = {
                "file": (path.name, file_obj, "application/octet-stream")
            }

            response = requests.post(
                HUB_INGEST_URL,
                files=files,
                data={"packet_id": packet_id},
                timeout=HTTP_TIMEOUT_SEC,
            )

        if response.status_code == 200:
            logger.info(
                "Packet basariyla gonderildi",
                extra={
                    "event": "packet_send_success",
                    "file_name": path.name,
                    "status_code": response.status_code,
                },
            )

            logger.info(
                "Hub response alindi",
                extra={
                    "event": "hub_response_received",
                    "file_name": path.name,
                    "response_body": response.text,
                },
            )
            return True

        logger.warning(
            "Hub hata dondu",
            extra={
                "event": "packet_send_http_error",
                "file_name": path.name,
                "status_code": response.status_code,
                "response_body": response.text,
            },
        )
        return False

    except requests.RequestException as exc:
        logger.error(
            "Packet gonderimi exception",
            extra={
                "event": "packet_send_exception",
                "file_name": path.name,
                "error": str(exc),
            },
        )
        return False