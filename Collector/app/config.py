import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PENDING_DIR = DATA_DIR / "pending"
SENDING_DIR = DATA_DIR / "sending"
SENT_DIR = DATA_DIR / "sent"
FAILED_DIR = DATA_DIR / "failed"
META_DIR = DATA_DIR / "meta"
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "collector.log"
COUNTER_FILE = DATA_DIR / "packet_counter.txt"

# Sampling config
TARGET_FS_HZ = 3200
PACKET_DURATION_SEC = 10
SAMPLES_PER_PACKET = TARGET_FS_HZ * PACKET_DURATION_SEC

# Packet/file config
PACKET_PREFIX = "packet"
FILE_FORMAT = "parquet"
PARQUET_COMPRESSION = "snappy"

# Transfer / retry config
HUB_INGEST_URL = os.environ.get("HUB_INGEST_URL", "http://127.0.0.1:8000/ingest")
HTTP_TIMEOUT_SEC = 30
MAX_RETRY_COUNT = 5
RETRY_INTERVAL_SEC = 5

# Runtime defaults
DEFAULT_MODE = "realtime"
DEFAULT_HOURS = 12.0
DEFAULT_ACCELERATION_FACTOR = 10.0

# Geri basınç ayarları
ENABLE_BACKPRESSURE = True
MAX_PENDING_PACKETS = 2
BACKPRESSURE_SLEEP_SEC = 5

# Saklama politikasi
MAX_SENT_PACKETS = 50
MAX_FAILED_PACKETS = 100




def ensure_directories() -> None:
    for path in [
        DATA_DIR,
        PENDING_DIR,
        SENDING_DIR,
        SENT_DIR,
        FAILED_DIR,
        META_DIR,
        LOG_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)