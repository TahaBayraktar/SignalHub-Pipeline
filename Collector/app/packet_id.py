import uuid


PACKET_NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")


def build_packet_id(
    packet_index: int,
    start_ts_ns: int,
    end_ts_ns: int,
    checksum: str,
) -> str:
    raw = f"{packet_index}:{start_ts_ns}:{end_ts_ns}:{checksum}"
    return str(uuid.uuid5(PACKET_NAMESPACE, raw))