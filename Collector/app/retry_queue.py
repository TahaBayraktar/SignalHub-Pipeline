from pathlib import Path
import shutil

from app.config import (
    PENDING_DIR,
    SENDING_DIR,
    SENT_DIR,
    FAILED_DIR,
    MAX_RETRY_COUNT,
)
from app.meta_store import (
    increment_retry,
    load_meta,
    mark_attempt_success,
    move_meta_for_packet,
)
from app.sender import send_packet

from app.cleanup import cleanup_sent_dir, cleanup_failed_dir
from app.config import MAX_SENT_PACKETS, MAX_FAILED_PACKETS
from app.logger import get_logger

logger = get_logger("collector.retry_queue")


def flush_pending_packets() -> None:
    """
    pending klasöründeki packet dosyalarını Hub'a göndermeyi dener.
    Başarılı olanları sent klasörüne taşır.
    Retry limiti aşanları failed klasörüne taşır.
    Başarısız olanları tekrar pending'e alır.
    """
    packet_files = sorted(PENDING_DIR.glob("*.parquet"))

    if not packet_files:
        logger.info(
            "Pending klasorunde gonderilecek packet yok",
            extra={
                "event": "pending_empty",
            },
        )
        return

    logger.info(
        "Pending klasorunde packet bulundu",
        extra={
            "event": "pending_found",
            "pending_count": len(packet_files),
        },
    )

    for pending_file_path in packet_files:
        logger.info(
            "Gonderim tekrar deneniyor",
            extra={
                "event": "packet_retry_attempt",
                "file_name": pending_file_path.name,
            },
        )

        # Önce sending klasörüne taşı
        sending_file_path = SENDING_DIR / pending_file_path.name
        shutil.move(str(pending_file_path), str(sending_file_path))

        meta = load_meta(sending_file_path)
        packet_id = meta["packet_id"]

        send_ok = send_packet(sending_file_path, packet_id)

        if send_ok:
            mark_attempt_success(sending_file_path)

            sent_file_path = SENT_DIR / sending_file_path.name
            shutil.move(str(sending_file_path), str(sent_file_path))
            move_meta_for_packet(sending_file_path, SENT_DIR)

            logger.info(
                "Packet sent klasorune tasindi",
                extra={
                    "event": "packet_sent",
                    "file_name": sent_file_path.name,
                },
            )
            cleanup_sent_dir(MAX_SENT_PACKETS)
        else:
            meta = increment_retry(
                sending_file_path,
                error_message="Hub gonderimi basarisiz",
            )
            retry_count = int(meta.get("retry_count", 0))

            logger.warning(
                "Retry sayisi guncellendi",
                extra={
                    "event": "retry_incremented",
                    "retry_count": retry_count,
                    "file_name": sending_file_path.name,
                },
            )

            if retry_count >= MAX_RETRY_COUNT:
                failed_file_path = FAILED_DIR / sending_file_path.name
                shutil.move(str(sending_file_path), str(failed_file_path))
                move_meta_for_packet(sending_file_path, FAILED_DIR)

                logger.error(
                    "Packet failed klasorune tasindi",
                    extra={
                        "event": "packet_failed",
                        "file_name": failed_file_path.name,
                        "retry_count": retry_count,
                    },
                )
                cleanup_failed_dir(MAX_FAILED_PACKETS)
            else:
                back_to_pending_path = PENDING_DIR / sending_file_path.name
                shutil.move(str(sending_file_path), str(back_to_pending_path))

                logger.warning(
                    "Packet tekrar pending klasorune alindi",
                    extra={
                        "event": "packet_requeued",
                        "file_name": back_to_pending_path.name,
                        "retry_count": retry_count,
                    },
                )