from dataclasses import dataclass


@dataclass
class SampleRecord:
    ts_ns: int
    x: float
    y: float
    z: float
    fs_hz: int
    seq: int


@dataclass
class PacketMeta:
    packet_index: int
    start_ts_ns: int
    end_ts_ns: int
    n_samples: int
    file_path: str
    checksum: str | None = None
    effective_hz: float | None = None
    packet_id: str | None = None