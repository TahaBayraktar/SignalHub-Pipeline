from app.db import fetch_one, execute


def packet_exists(checksum: str) -> bool:
    row = fetch_one(
        "SELECT 1 FROM packets WHERE checksum = %s",
        (checksum,),
    )
    return row is not None


def insert_packet(packet_id: str, checksum: str, file_name: str, file_path: str):
    execute(
        """
        INSERT INTO packets (packet_id, checksum, file_name, file_path, status)
        VALUES (%s, %s, %s, %s, 'raw')
        """,
        (packet_id, checksum, file_name, file_path),
    )

def update_packet_status(packet_id: str, status: str, error: str | None = None):
    execute(
        """
        UPDATE packets
        SET status = %s,
            last_error = %s,
            processed_at = CASE WHEN %s = 'processed' THEN NOW() ELSE processed_at END
        WHERE packet_id = %s
        """,
        (status, error, status, packet_id),
    )

def insert_packet_metrics(packet_id: str, metrics: dict):
    execute(
        """
        INSERT INTO packet_metrics (
            packet_id,
            downsample_method,
            mean_x, mean_y, mean_z,
            rms_x, rms_y, rms_z,
            peak_x, peak_y, peak_z
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            packet_id,
            metrics["downsample_method"],
            metrics["mean_x"],
            metrics["mean_y"],
            metrics["mean_z"],
            metrics["rms_x"],
            metrics["rms_y"],
            metrics["rms_z"],
            metrics["peak_x"],
            metrics["peak_y"],
            metrics["peak_z"],
        ),
    )

def get_summary() -> dict:
    row = fetch_one(
        """
        SELECT
            COUNT(*) AS total_packets,
            COUNT(*) FILTER (WHERE p.status = 'processed') AS processed_packets,
            COUNT(*) FILTER (WHERE p.status = 'failed') AS failed_packets,
            AVG(m.mean_x) AS avg_mean_x,
            AVG(m.mean_y) AS avg_mean_y,
            AVG(m.mean_z) AS avg_mean_z,
            AVG(m.rms_x) AS avg_rms_x,
            AVG(m.rms_y) AS avg_rms_y,
            AVG(m.rms_z) AS avg_rms_z,
            MAX(m.peak_x) AS max_peak_x,
            MAX(m.peak_y) AS max_peak_y,
            MAX(m.peak_z) AS max_peak_z
        FROM packets p
        LEFT JOIN packet_metrics m
            ON p.packet_id = m.packet_id
        """
    )

    return dict(row) if row else {}

def get_packet_file_path(packet_id: str) -> str | None:
    row = fetch_one(
        """
        SELECT file_path
        FROM packets
        WHERE packet_id = %s
        """,
        (packet_id,),
    )

    if not row:
        return None

    return row["file_path"]

def update_packet_file_path(packet_id: str, file_path: str):
    execute(
        """
        UPDATE packets
        SET file_path = %s
        WHERE packet_id = %s
        """,
        (file_path, packet_id),
    )

def insert_packet_event(packet_id: str, event_type: str, message: str | None = None):
    execute(
        """
        INSERT INTO packet_events (packet_id, event_type, message)
        VALUES (%s, %s, %s)
        """,
        (packet_id, event_type, message),
    )

def get_metrics() -> dict:
    row = fetch_one(
        """
        SELECT
            COUNT(*) AS total_packets,
            COUNT(*) FILTER (WHERE status = 'processed') AS processed_packets,
            COUNT(*) FILTER (WHERE status = 'failed') AS failed_packets,
            COUNT(*) FILTER (WHERE status = 'raw') AS raw_packets
        FROM packets
        """
    )

    return {
        "total_packets": int(row["total_packets"]) if row else 0,
        "processed_packets": int(row["processed_packets"]) if row else 0,
        "failed_packets": int(row["failed_packets"]) if row else 0,
        "raw_packets": int(row["raw_packets"]) if row else 0,
    }


def cleanup_old_packet_events(retention_days: int) -> None:
    execute(
        """
        DELETE FROM packet_events
        WHERE created_at < NOW() - (%s || ' days')::interval
        """,
        (retention_days,),
    )