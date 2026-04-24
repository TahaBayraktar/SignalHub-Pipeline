import time
import sys
import os


sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sensor_sim import read_xyz
from app.config import TARGET_FS_HZ
from app.models import SampleRecord


def collect_sample(seq: int) -> SampleRecord:
    x, y, z = read_xyz()

    return SampleRecord(
        ts_ns=time.time_ns(),
        x=float(x),
        y=float(y),
        z=float(z),
        fs_hz=TARGET_FS_HZ,
        seq=seq,
    )