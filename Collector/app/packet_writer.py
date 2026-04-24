from datetime import datetime

import pandas as pd

from app.checksum import calculate_sha256
from app.config import PENDING_DIR, PACKET_PREFIX, FILE_FORMAT, PARQUET_COMPRESSION
from app.meta_store import create_meta_file
from app.models import SampleRecord, PacketMeta
from app.packet_id import build_packet_id


def write_packet(samples: list[SampleRecord], packet_index: int) -> PacketMeta:
    """
    SampleRecord listesini Parquet dosyası olarak yazar.
    PacketMeta döner.
    """
    if not samples:
        raise ValueError("Bos sample listesi packet olarak yazilamaz.")

    rows = [
        {
            "ts_ns": sample.ts_ns,
            "x": sample.x,
            "y": sample.y,
            "z": sample.z,
            "fs_hz": sample.fs_hz,
            "seq": sample.seq,
        }
        for sample in samples
    ]

    df = pd.DataFrame(rows).astype({
        "ts_ns": "int64",
        "x": "float32",
        "y": "float32",
        "z": "float32",
        "fs_hz": "int32",
        "seq": "int64",
    })

    start_ts_ns = samples[0].ts_ns
    end_ts_ns = samples[-1].ts_ns
    n_samples = len(samples)

    duration_ns = end_ts_ns - start_ts_ns
    effective_hz = 0.0
    if duration_ns > 0:
        duration_sec = duration_ns / 1_000_000_000
        effective_hz = n_samples / duration_sec

    created_at = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = (
        f"{PACKET_PREFIX}_{packet_index}_{start_ts_ns}_{end_ts_ns}_{created_at}.{FILE_FORMAT}"
    )
    file_path = PENDING_DIR / filename

    df.to_parquet(
        file_path,
        index=False,
        compression=PARQUET_COMPRESSION,
    )

    checksum = calculate_sha256(file_path)

    packet_id = build_packet_id(
        packet_index=packet_index,
        start_ts_ns=start_ts_ns,
        end_ts_ns=end_ts_ns,
        checksum=checksum,
    )

    packet_meta = PacketMeta(
        packet_index=packet_index,
        start_ts_ns=start_ts_ns,
        end_ts_ns=end_ts_ns,
        n_samples=n_samples,
        file_path=str(file_path),
        checksum=checksum,
        effective_hz=effective_hz,
        packet_id=packet_id,
    )

    create_meta_file(packet_meta)

    return packet_meta