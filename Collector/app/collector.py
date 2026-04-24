import argparse
import time
from threading import Thread

from app.config import (
    ensure_directories,
    TARGET_FS_HZ,
    SAMPLES_PER_PACKET,
    PACKET_DURATION_SEC,
    DEFAULT_MODE,
    DEFAULT_HOURS,
    DEFAULT_ACCELERATION_FACTOR,
    ENABLE_BACKPRESSURE,
    MAX_PENDING_PACKETS,
    BACKPRESSURE_SLEEP_SEC,
    PENDING_DIR,
)
from app.counter_store import get_current_packet_index, increment_packet_index
from app.health_server import start_health_server, update_last_packet_time
from app.logger import get_logger
from app.packet_writer import write_packet
from app.retry_queue import flush_pending_packets
from app.sampler import collect_sample

logger = get_logger("collector")


def parse_args():
    parser = argparse.ArgumentParser(description="Predwise Collector")

    parser.add_argument(
        "--mode",
        choices=["realtime", "accelerated"],
        help="Calisma modu",
    )

    parser.add_argument(
        "--hours",
        type=float,
        help="Toplam kac saatlik veri uretilecegi",
    )

    parser.add_argument(
        "--acceleration",
        type=float,
        help="Hizlandirma katsayisi. Sadece accelerated modda anlamli",
    )

    return parser.parse_args()


def calculate_packet_count(hours: float) -> int:
    total_seconds = hours * 3600
    packet_count = int(total_seconds / PACKET_DURATION_SEC)
    return max(packet_count, 1)


def apply_backpressure_if_needed():
    if not ENABLE_BACKPRESSURE:
        return

    while True:
        pending_count = len(list(PENDING_DIR.glob("*.parquet")))

        if pending_count <= MAX_PENDING_PACKETS:
            return

        logger.warning(
            "Geri basinc aktif",
            extra={
                "event": "backpressure_triggered",
                "pending_count": pending_count,
                "max_pending_packets": MAX_PENDING_PACKETS,
            },
        )

        logger.info(
            "Pending queue flush ediliyor",
            extra={
                "event": "pending_flush_requested",
                "pending_count": pending_count,
            },
        )
        flush_pending_packets()

        logger.info(
            "Bekleme uygulanacak",
            extra={
                "event": "backpressure_sleep",
                "sleep_seconds": BACKPRESSURE_SLEEP_SEC,
            },
        )
        time.sleep(BACKPRESSURE_SLEEP_SEC)


def collect_samples(count: int, target_hz: int, mode: str, acceleration: float):
    buffer = []

    base_interval_sec = 1.0 / target_hz

    if mode == "accelerated":
        sleep_interval_sec = base_interval_sec / acceleration
    else:
        sleep_interval_sec = base_interval_sec

    next_sample_time = time.perf_counter()

    for seq in range(count):
        now = time.perf_counter()

        if now < next_sample_time:
            time.sleep(next_sample_time - now)

        sample = collect_sample(seq)
        buffer.append(sample)

        next_sample_time += sleep_interval_sec

    return buffer


def run_collector(packet_limit: int, mode: str, acceleration: float):
    packet_index = get_current_packet_index()
    produced_count = 0

    while produced_count < packet_limit:
        apply_backpressure_if_needed()

        logger.info(
            "Yeni packet toplaniyor",
            extra={
                "event": "packet_collect_start",
                "packet_index": packet_index,
            },
        )

        if mode == "accelerated":
            logger.info(
                "Accelerated mode aktif",
                extra={
                    "event": "collector_mode_accelerated",
                    "packet_index": packet_index,
                    "acceleration_factor": acceleration,
                },
            )
        else:
            logger.info(
                "Real-time mode aktif",
                extra={
                    "event": "collector_mode_realtime",
                    "packet_index": packet_index,
                },
            )

        buffer = collect_samples(
            count=SAMPLES_PER_PACKET,
            target_hz=TARGET_FS_HZ,
            mode=mode,
            acceleration=acceleration,
        )

        logger.info(
            "Olcumler toplandi",
            extra={
                "event": "samples_collected",
                "packet_index": packet_index,
                "sample_count": len(buffer),
            },
        )

        packet_meta = write_packet(buffer, packet_index=packet_index)
        update_last_packet_time()

        logger.info(
            "Packet metadata olusturuldu",
            extra={
                "event": "packet_written",
                "packet_index": packet_meta.packet_index,
                "file_name": packet_meta.file_path.split("/")[-1],
                "sample_count": packet_meta.n_samples,
                "effective_hz": packet_meta.effective_hz,
            },
        )

        logger.info(
            "Pending queue flush ediliyor",
            extra={
                "event": "pending_flush_requested",
                "packet_index": packet_index,
            },
        )
        flush_pending_packets()

        packet_index = increment_packet_index()
        produced_count += 1

    logger.info(
        "Collector calismasi tamamlandi",
        extra={
            "event": "collector_run_completed",
            "produced_packet_count": produced_count,
        },
    )


def main():
    ensure_directories()
    logger.info(
        "Collector basladi",
        extra={
            "event": "collector_started",
        },
    )

    health_thread = Thread(target=start_health_server, daemon=True)
    health_thread.start()

    args = parse_args()

    # CLI verilmezse config defaultlarini kullan
    mode = args.mode if args.mode is not None else DEFAULT_MODE
    hours = args.hours if args.hours is not None else DEFAULT_HOURS
    acceleration = (
        args.acceleration
        if args.acceleration is not None
        else DEFAULT_ACCELERATION_FACTOR
    )

    packet_limit = calculate_packet_count(hours)

    logger.info(
        "Program baslangicinda pending packetler kontrol ediliyor",
        extra={
            "event": "startup_pending_flush",
        },
    )
    flush_pending_packets()

    logger.info(
        "Collector calisma ayarlari belirlendi",
        extra={
            "event": "collector_config_selected",
            "mode": mode,
            "hours": hours,
            "packet_limit": packet_limit,
        },
    )

    if mode == "accelerated":
        logger.info(
            "Hizlandirma katsayisi belirlendi",
            extra={
                "event": "acceleration_config_selected",
                "acceleration_factor": acceleration,
            },
        )

    run_collector(
        packet_limit=packet_limit,
        mode=mode,
        acceleration=acceleration,
    )


if __name__ == "__main__":
    main()