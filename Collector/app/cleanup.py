from pathlib import Path

from app.config import SENT_DIR, FAILED_DIR
from app.logger import get_logger


logger = get_logger("collector.cleanup")

def cleanup_old_packets(target_dir: Path, max_files: int) -> None:
    """
    Bir klasördeki parquet ve json dosyalarini dosya sayisina gore sinirlar.
    En eski packetler silinir.
    """
    if max_files <= 0:
        raise ValueError("max_files pozitif bir sayi olmalidir.")

    packet_files = sorted(
        target_dir.glob("*.parquet"),
        key=lambda p: p.stat().st_mtime
    )

    if len(packet_files) <= max_files:
        return

    files_to_delete = packet_files[: len(packet_files) - max_files]

    for packet_file in files_to_delete:
        meta_file = target_dir / f"{packet_file.stem}.json"

        if packet_file.exists():
            packet_file.unlink()

        if meta_file.exists():
            meta_file.unlink()

        logger.info(
            "Eski packet silindi",
            extra={
                "event": "packet_cleanup",
                "directory": target_dir.name,
                "file_name": packet_file.name,
            },
        )


def cleanup_sent_dir(max_files: int) -> None:
    cleanup_old_packets(SENT_DIR, max_files)


def cleanup_failed_dir(max_files: int) -> None:
    cleanup_old_packets(FAILED_DIR, max_files)