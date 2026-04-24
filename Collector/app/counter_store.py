from app.config import COUNTER_FILE


def _ensure_counter_file() -> None:
    if not COUNTER_FILE.exists():
        COUNTER_FILE.write_text("0", encoding="utf-8")


def get_current_packet_index() -> int:
    _ensure_counter_file()

    raw_value = COUNTER_FILE.read_text(encoding="utf-8").strip()
    if not raw_value:
        return 0

    return int(raw_value)


def increment_packet_index() -> int:
    current_value = get_current_packet_index()
    next_value = current_value + 1

    COUNTER_FILE.write_text(str(next_value), encoding="utf-8")

    return next_value