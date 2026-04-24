import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import META_DIR
from app.models import PacketMeta


def _meta_filename_from_packet_path(packet_path: str | Path) -> str:
    packet_path = Path(packet_path)
    return f"{packet_path.stem}.json"


def _meta_path_from_packet_path(packet_path: str | Path) -> Path:
    return META_DIR / _meta_filename_from_packet_path(packet_path)


def create_meta_file(packet_meta: PacketMeta) -> Path:
    meta_path = _meta_path_from_packet_path(packet_meta.file_path)

    payload = {
        "packet_id": packet_meta.packet_id,
        "packet_index": packet_meta.packet_index,
        "file_path": packet_meta.file_path,
        "checksum": packet_meta.checksum,
        "retry_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_attempt_at": None,
        "last_error": None,
    }

    meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return meta_path


def load_meta(packet_path: str | Path) -> dict:
    meta_path = _meta_path_from_packet_path(packet_path)

    if not meta_path.exists():
        raise FileNotFoundError(f"Meta dosyasi bulunamadi: {meta_path}")

    return json.loads(meta_path.read_text(encoding="utf-8"))


def save_meta(packet_path: str | Path, data: dict) -> Path:
    meta_path = _meta_path_from_packet_path(packet_path)
    meta_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return meta_path


def increment_retry(packet_path: str | Path, error_message: str | None = None) -> dict:
    data = load_meta(packet_path)
    data["retry_count"] = int(data.get("retry_count", 0)) + 1
    data["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
    data["last_error"] = error_message
    save_meta(packet_path, data)
    return data


def mark_attempt_success(packet_path: str | Path) -> dict:
    data = load_meta(packet_path)
    data["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
    data["last_error"] = None
    save_meta(packet_path, data)
    return data


def move_meta_for_packet(packet_path: str | Path, destination_dir: Path) -> Path:
    old_meta_path = _meta_path_from_packet_path(packet_path)
    new_meta_path = destination_dir / _meta_filename_from_packet_path(packet_path)

    if old_meta_path.exists():
        old_meta_path.replace(new_meta_path)

    return new_meta_path